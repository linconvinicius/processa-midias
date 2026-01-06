from src.database.connection import DatabaseConnection
import pyodbc

class SocialMediaRepository:
    def __init__(self):
        self._db = DatabaseConnection()
        self.conn = self._db.get_connection()
    
    def _ensure_connection(self):
        """Checks if connection is alive and attempts to reconnect if not."""
        try:
            # Simple check query
            self.conn.cursor().execute("SELECT 1")
        except (pyodbc.Error, pyodbc.ProgrammingError, AttributeError):
            print("🔄 Database connection lost. Reconnecting...")
            try:
                if self.conn:
                    try: self.conn.close()
                    except: pass
                self.conn = self._db.get_connection()
                print("✅ Reconnected to database.")
            except Exception as e:
                print(f"❌ Failed to reconnect: {e}")
                raise
    
    def get_link_by_id(self, link_id: int):
        """Fetches a single link by ID."""
        self._ensure_connection()
        cursor = self.conn.cursor()
        query = """
        SELECT 
            LIMW_CD_LINK_MIDIA_SOCIAL_WEB, 
            LIMW_TX_LINK, 
            VEIC_CD_VEICULO, 
            CANA_CD_CANAL, 
            CLIE_CD_CLIENTE, 
            LIMW_DT_DATA_PUBLICAÇÃO,
            LIMW_IN_STATUS,
            MATE_CD_MATERIA
        FROM TopClipPreProducao.dbo.Link_MidiaSocial_Web
        WHERE LIMW_CD_LINK_MIDIA_SOCIAL_WEB = ?
        """
        try:
            cursor.execute(query, (link_id,))
            row = cursor.fetchone()
            if row:
                columns = [column[0] for column in cursor.description]
                return dict(zip(columns, row))
            return None
        finally:
            cursor.close()
    
    def get_pending_links(self, limit: int = 10, client_id: int = None, platform: str = None):
        """
        Fetches pending links from Link_MidiaSocial_Web.
        Status 1 = Pending, 9 = Retry.
        Platform: 'instagram', 'facebook', or None (all)
        """
        self._ensure_connection()
        cursor = self.conn.cursor()
        
        # Base query
        query = """
        SELECT TOP (?) 
            LIMW_CD_LINK_MIDIA_SOCIAL_WEB, 
            LIMW_TX_LINK, 
            VEIC_CD_VEICULO, 
            CANA_CD_CANAL, 
            CLIE_CD_CLIENTE, 
            CLIE_CD_CLIENTE, 
            LIMW_DT_DATA_PUBLICAÇÃO,
            MATE_CD_MATERIA
        FROM TopClipPreProducao.dbo.Link_MidiaSocial_Web
        WHERE LIMW_IN_STATUS IN (1, 9) 
          AND LIMW_DT_DATA_PUBLICAÇÃO >= DATEADD(day, -15, GETDATE())
        """
        
        params = [limit]
        
        if platform:
            plat_lower = platform.lower()
            if 'twitter' in plat_lower or 'x.com' in plat_lower:
                query += " AND (LIMW_TX_LINK LIKE '%twitter.com%' OR LIMW_TX_LINK LIKE '%x.com%')"
            elif 'instagram' in plat_lower:
                query += " AND LIMW_TX_LINK LIKE '%instagram.com%'"
            elif 'facebook' in plat_lower:
                query += " AND (LIMW_TX_LINK LIKE '%facebook.com%' OR LIMW_TX_LINK LIKE '%fb.com%' OR LIMW_TX_LINK LIKE '%fb.watch%')"
            else:
                query += " AND LIMW_TX_LINK LIKE ?"
                params.append(f"%{platform}%")
            
        if client_id:
            query += " AND CLIE_CD_CLIENTE = ?"
            params.append(client_id)
            
        query += " ORDER BY LIMW_CD_LINK_MIDIA_SOCIAL_WEB DESC"
        
        try:
            cursor.execute(query, params)
            columns = [column[0] for column in cursor.description]
            results = []
            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))
            return results
        except Exception as e:
            print(f"Error fetching links: {e}")
            return []
        finally:
            cursor.close()

    def update_link_status(self, link_id: int, status: int, materia_id: int = None):
        """Updates status and optionally materia_id."""
        self._ensure_connection()
        cursor = self.conn.cursor()
        if materia_id:
            query = "UPDATE TopClipPreProducao.dbo.Link_MidiaSocial_Web SET LIMW_IN_STATUS = ?, MATE_CD_MATERIA = ? WHERE LIMW_CD_LINK_MIDIA_SOCIAL_WEB = ?"
            params = (status, materia_id, link_id)
        else:
            query = "UPDATE TopClipPreProducao.dbo.Link_MidiaSocial_Web SET LIMW_IN_STATUS = ? WHERE LIMW_CD_LINK_MIDIA_SOCIAL_WEB = ?"
            params = (status, link_id)
            
        try:
            cursor.execute(query, *params)
            self.conn.commit()
        except Exception as e:
            print(f"Error updating status for {link_id}: {e}")
            self.conn.rollback()
        finally:
            cursor.close()

    def check_existing_url(self, url: str):
        """Checks if a URL already exists."""
        self._ensure_connection()
        cursor = self.conn.cursor()
        query = "SELECT COUNT(*) FROM TopClipPreProducao.dbo.Link_MidiaSocial_Web WHERE LIMW_TX_LINK = ?"
        try:
            cursor.execute(query, (url,))
            count = cursor.fetchone()[0]
            return count > 0
        except Exception as e:
            print(f"Error checking URL: {e}")
            return False
        finally:
            cursor.close()

    def delete_materia_by_link(self, link_id: int):
        """Deletes Materia associated with a link and clears the reference."""
        self._ensure_connection()
        cursor = self.conn.cursor()
        
        try:
            # 1. Get materia_id associated with this link
            cursor.execute("SELECT MATE_CD_MATERIA FROM TopClipPreProducao.dbo.Link_MidiaSocial_Web WHERE LIMW_CD_LINK_MIDIA_SOCIAL_WEB = ?", (link_id,))
            row = cursor.fetchone()
            
            if row and row[0]:
                materia_id = row[0]
                # 2. Delete from Materia table
                cursor.execute("DELETE FROM TopClipPreProducao.dbo.Materia WHERE MATE_CD_MATERIA = ?", (materia_id,))
                
                # 3. Clear reference in Link table
                cursor.execute("UPDATE TopClipPreProducao.dbo.Link_MidiaSocial_Web SET MATE_CD_MATERIA = NULL WHERE LIMW_CD_LINK_MIDIA_SOCIAL_WEB = ?", (link_id,))
                
                self.conn.commit()
                print(f"✅ Materia {materia_id} deleted and link {link_id} cleared.")
            else:
                print(f"ℹ️ No Materia associated with link {link_id}.")
                
        except Exception as e:
            print(f"Error deleting materia for link {link_id}: {e}")
            self.conn.rollback()
        finally:
            cursor.close()

    def close(self):
        self.conn.close()
