import asyncio
import argparse
import logging
import sys
from src.services.processing_service import SocialMediaProcessor

# Ensure terminal encoding handles emojis/UTF-8
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        # Fallback for older python
        pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)

async def main():
    parser = argparse.ArgumentParser(description='Social Media Processor CLI')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Process command
    process_parser = subparsers.add_parser('process', help='Process social media links')
    process_parser.add_argument('--id', nargs='+', help='Process specific link IDs (supports comma-separated list)')
    process_parser.add_argument('--batch', action='store_true', help='Process a batch of links')
    process_parser.add_argument('--limit', type=int, default=10, help='Number of links to process in batch')
    process_parser.add_argument('--platform', type=str, help='Filter by platform (Instagram, Twitter, Facebook)')

    # Verify command
    verify_parser = subparsers.add_parser('verify', help='Verify database connection')

    # Reset command
    reset_parser = subparsers.add_parser('reset', help='Reset link status to pending')
    reset_parser.add_argument('--id', nargs='+', required=True, help='Link IDs to reset (supports comma-separated list)')

    # Queue command
    queue_parser = subparsers.add_parser('queue', help='Show pending links in queue')
    queue_parser.add_argument('--limit', type=int, default=10, help='Number of links to show')
    queue_parser.add_argument('--platform', type=str, help='Filter by platform')

    args = parser.parse_args()

    processor = SocialMediaProcessor()

    try:
        if args.command == 'process':
            if args.id:
                # Parse multiple IDs which might contain commas
                target_ids = []
                for id_str in args.id:
                    # Split by comma and clean up whitespace/punctuation
                    parts = [p.strip(' ,').strip() for p in id_str.split(',')]
                    for p in parts:
                        if p.isdigit():
                            target_ids.append(int(p))
                
                if not target_ids:
                    print("❌ No valid IDs found.")
                    return

                await processor.initialize()
                for lid in target_ids:
                    print(f"🚀 Processing link {lid}...")
                    await processor.process_link(lid)
            elif args.batch:
                await processor.process_batch(limit=args.limit, platform=args.platform)
            else:
                print("Please specify --id or --batch")
        
        elif args.command == 'verify':
            from src.database.connection import DatabaseConnection
            db = DatabaseConnection()
            conn = db.get_connection()
            print("✅ Database connection successful!")
            conn.close()
        
        elif args.command == 'reset':
            # Parse multiple IDs which might contain commas
            target_ids = []
            for id_str in args.id:
                parts = [p.strip(' ,').strip() for p in id_str.split(',')]
                for p in parts:
                    if p.isdigit():
                        target_ids.append(int(p))
            
            if not target_ids:
                print("❌ No valid IDs found to reset.")
                return

            for lid in target_ids:
                processor.repo.delete_materia_by_link(lid)
                processor.repo.update_link_status(lid, 1)
                print(f"✅ Link {lid} fully reset to Pending (1).")
        
        elif crud_command := args.command == 'queue':
            links = processor.repo.get_pending_links(limit=args.limit, platform=args.platform)
            if not links:
                print("📭 Fila vazia.")
            else:
                print(f"📋 Fila de Processamento ({len(links)} links):")
                print(f"{'ID':<10} | {'Plataforma':<12} | {'URL'}")
                print("-" * 60)
                for link in links:
                    url = link['LIMW_TX_LINK']
                    # Simple platform detection
                    plat = "Unknown"
                    if "facebook.com" in url: plat = "Facebook"
                    elif "twitter.com" in url or "x.com" in url: plat = "Twitter"
                    elif "instagram.com" in url: plat = "Instagram"
                    
                    print(f"{link['LIMW_CD_LINK_MIDIA_SOCIAL_WEB']:<10} | {plat:<12} | {url[:80]}...")
        
        else:
            parser.print_help()

    except Exception as e:
        logger.error(f"Error in CLI: {e}")
    finally:
        await processor.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
