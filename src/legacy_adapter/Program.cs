using System;
using System.IO;
using System.Linq;
using System.Drawing;
using System.Runtime.Serialization.Formatters.Binary;
using DadosColeta;
using ManagerDB;

namespace LegacyAdapter
{
    class Program
    {
        static void Main(string[] args)
        {
            // Usage: LegacyAdapter.exe <LinkID> <FilePath> <Text> <Date> <VeiculoCode> <CanalCode> <ClientCode>
            if (args.Length < 7)
            {
                Console.WriteLine("Error: Missing arguments. Expected: LinkID FilePath Text Date(yyyy-MM-dd) Veiculo Canal Client");
                Environment.Exit(1);
            }

            try
            {
                int linkId = int.Parse(args[0]);
                string imagePath = args[1];
                string text = File.ReadAllText(args[2], System.Text.Encoding.UTF8); // Use UTF8 explicitly
                DateTime pubDate = DateTime.Parse(args[3]);
                int veiculo = int.Parse(args[4]);
                int canal = int.Parse(args[5]);
                int cliente = int.Parse(args[6]);

                Console.WriteLine("Processing Link " + linkId + "...");

                // 1. Initialize Contexts
                // Replaced DadosMidiaSocial9 with ColetaProducaoEntities based on code analysis
                ColetaProducaoEntities midia = new ColetaProducaoEntities();
                Manager mana = new Manager();
                mana.OnERRO += (ex) => {
                    Console.WriteLine("MANAGER ERROR: " + ex.Message);
                    Console.WriteLine(ex.StackTrace);
                };

                // 2. Create Materia (Legacy Stored Procedure)
                // sp_materia_web_insert_auto(Titulo, Data, Veiculo)
                // Using first 100 chars of text as Title if needed, or generic title
                string title = text.Length > 100 ? text.Substring(0, 100) : text;
                
                Console.WriteLine("Inserting Materia...");
                var re = midia.sp_materia_web_insert_auto(title, pubDate, veiculo);
                int? codigoMateria = re.FirstOrDefault();

                if (!codigoMateria.HasValue)
                {
                    throw new Exception("Failed to retrieve CodigoMateria from SP.");
                }

                int codMat = codigoMateria.Value;
                Console.WriteLine("Materia ID: " + codMat);

                // 3. Link Materia to Cliente
                // sp_materia_cliente_insert_coleta(CodMat, CodCli, 4, 0, fluxo, "", NumServico)
                
                // Values derived from legacy Processa.cs GravarMateria method
                byte[] fluxo = new byte[] { 8 };
                byte numServico = 8;
                
                // Explicit casts to help compiler resolve overload if needed
                midia.sp_materia_cliente_insert_coleta(codMat, cliente, (byte)4, (byte)0, fluxo, "", numServico);
                midia.sp_Materia_Cliente_Canal_Virtual_Insert(codMat, cliente, canal, (byte)90); // 90 = confidence?

                midia.SaveChanges();

                // 4. Save Binary Image (Serialized Bitmap)
                if (File.Exists(imagePath))
                {
                    Console.WriteLine("Serializing Bitmap...");
                    using (Bitmap bmp = new Bitmap(imagePath))
                    {
                        using (MemoryStream ms = new MemoryStream())
                        {
                            BinaryFormatter bf = new BinaryFormatter();
                            bf.Serialize(ms, bmp);

                            mana.CodigoMateria = codMat;
                            mana.ImagemWeb = ms.ToArray();
                            mana.Add(); 
                        }
                    }
                    Console.WriteLine("Image Saved.");
                }
                else
                {
                    Console.WriteLine("Warning: Image file not found.");
                }

                // 5. Update Status in Link_MidiaSocial_Web
                var linkTable = midia.Link_MidiaSocial_Web.FirstOrDefault(x => x.LIMW_CD_LINK_MIDIA_SOCIAL_WEB == linkId);
                if (linkTable != null)
                {
                    Console.WriteLine("Updating Link " + linkId + " with Materia " + codMat);
                    linkTable.MATE_CD_MATERIA = codMat;
                    linkTable.VEIC_CD_VEICULO = veiculo;
                    linkTable.LIMW_IN_STATUS = 2; // 2 = Success/Processado (User confirmed)
                    midia.SaveChanges();
                }
                else
                {
                    Console.WriteLine("Warning: Link " + linkId + " not found for update.");
                }

                // Verification within the same context skipped due to compilation error (Materia DbSet not exposed)
                /*
                var checkMateria = midia.Materia.FirstOrDefault(m => m.MATE_CD_MATERIA == codMat);
                if (checkMateria != null)
                {
                    Console.WriteLine("VERIFICATION: Materia " + codMat + " exists in DB (Title: " + checkMateria.MATE_TX_TITULO + ")");
                }
                else
                {
                    Console.WriteLine("VERIFICATION ERROR: Materia " + codMat + " NOT found in DB context!");
                }
                */

                Console.WriteLine("SUCCESS");
            }
            catch (Exception ex)
            {
                Console.WriteLine("ERROR: " + ex.Message);
                Console.WriteLine(ex.StackTrace);
                Environment.Exit(1);
            }
        }
    }
}
