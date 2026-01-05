import logging
import asyncio
from datetime import datetime
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential
from src.database.repository import SocialMediaRepository
from src.scraper.core.browser import BrowserManager
from src.scraper.spiders.instagram import InstagramSpider
from src.scraper.spiders.twitter import TwitterSpider
from src.scraper.spiders.facebook import FacebookSpider
from src.legacy_adapter.run_adapter import run_legacy_adapter

logger = logging.getLogger(__name__)

class SocialMediaProcessor:
    def __init__(self):
        self.repo = SocialMediaRepository()
        self.browser_manager = None
        self.spiders = {}

    async def initialize(self):
        if not self.browser_manager:
            self.browser_manager = BrowserManager()
            await self.browser_manager.start()
            
            self.spiders = {
                'instagram': InstagramSpider(self.browser_manager),
                'twitter': TwitterSpider(self.browser_manager),
                'facebook': FacebookSpider(self.browser_manager)
            }
            logger.info("Browser and Spiders initialized.")

    async def process_link(self, link_id: int):
        """Process a single link by ID"""
        await self.initialize()
        
        logger.info(f"🚀 [Link {link_id}] - Iniciando processamento...")
        
        # Get link data
        link_data = self.repo.get_link_by_id(link_id)
        if not link_data:
            logger.error(f"Link {link_id} not found in database.")
            return False
        
        url = link_data['LIMW_TX_LINK']
        
        # Detect platform from URL
        platform = None
        if 'instagram.com' in url:
            platform = 'instagram'
        elif 'twitter.com' in url or 'x.com' in url:
            platform = 'twitter'
        elif 'facebook.com' in url:
            platform = 'facebook'
        
        if not platform:
            logger.error(f"Could not detect platform from URL: {url}")
            self.repo.update_link_status(link_id, 3)  # Error status
            return False
        
        logger.info(f"🔍 [Link {link_id}] - Passo 1: Preparando ambiente de captura...")
        
        spider = self.spiders.get(platform)
        if not spider:
            logger.error(f"No spider found for platform: {platform}")
            self.repo.update_link_status(link_id, 3)
            return False

        try:
            logger.info(f"🕷️ Scraping {url} via {platform} spider...")
            logger.info(f"📸 [Link {link_id}] - Passo 2: Capturando dados da rede social...")
            
            spider_input = {
                'url': url, 
                'link_id': link_id,
                'veiculo_code': link_data.get('VEIC_CD_VEICULO'),
                'canal_code': link_data.get('CANA_CD_CANAL'),
                'client_code': link_data.get('CLIE_CD_CLIENTE'),
                'pub_date': link_data.get('LIMW_DT_DATA_PUBLICAÇÃO')
            }
            
            # Retry logic for scraping
            async for attempt in AsyncRetrying(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10)):
                with attempt:
                    result = await spider.scrape_post(spider_input)
                    
                    if not result or result.get('status') != 'success':
                        raise Exception(result.get('error', 'Unknown scraping error'))
            
            logger.info(f"✅ Scraping success for Link {link_id}")
            
            # Get publication date
            pub_date = result.get('pub_date') or link_data.get('LIMW_DT_DATA_PUBLICAÇÃO')
            if isinstance(pub_date, datetime):
                pub_date_str = pub_date.strftime('%Y-%m-%d')
            else:
                pub_date_str = str(pub_date) if pub_date else datetime.now().strftime('%Y-%m-%d')
            
            logger.info(f"📅 Using Publication Date: {pub_date_str}")
            
            # Platform Specific Overrides (Legacy Consistency)
            # Codes found in VEICULO table:
            # Instagram = 54108
            # Twitter = 98411
            # Facebook = 24247
            
            if platform == 'instagram':
                spider_input['veiculo_code'] = 54108
            elif platform == 'twitter':
                spider_input['veiculo_code'] = 98411
            elif platform == 'facebook':
                spider_input['veiculo_code'] = 24247

            # Ensure numeric codes are not None before adapter call
            spider_input['veiculo_code'] = spider_input.get('veiculo_code') or 70963 # Generic "Rede Social" fallback
            spider_input['canal_code'] = spider_input.get('canal_code') or 0
            spider_input['client_code'] = spider_input.get('client_code') or 0
            
            # Call Legacy Adapter
            logger.info(f"🔄 invoking LegacyAdapter...")
            adapter_success = run_legacy_adapter(
                link_id=link_id,
                image_path=result['image_path'],
                text_path=result['text_path'],
                pub_date=pub_date_str,
                veiculo=spider_input['veiculo_code'],
                canal=spider_input['canal_code'],
                cliente=spider_input['client_code']
            )
            
            if adapter_success:
                logger.info(f"✅ LegacyAdapter execution finished.")
                self.repo.update_link_status(link_id, 2) # Success
                return True
            else:
                logger.error(f"❌ LegacyAdapter failed (returned False).")
                self.repo.update_link_status(link_id, 3) # Error
                return False
                
        except Exception as e:
            logger.error(f"Critical error processing link {link_id}: {e}")
            self.repo.update_link_status(link_id, 3) # Error
            import traceback
            traceback.print_exc()
            return False

    async def process_batch(self, limit: int = 10, platform: str = None):
        logger.info(f"Fetching {limit} pending links (Platform: {platform or 'All'})...")
        links = self.repo.get_pending_links(limit=limit, platform=platform)

        if not links:
            logger.info("No pending links found.")
            return

        logger.info(f"Found {len(links)} links. Starting batch...")

        success_count = 0
        await self.initialize()

        for link in links:
            lid = link['LIMW_CD_LINK_MIDIA_SOCIAL_WEB']
            success = await self.process_link(lid)
            if success:
                success_count += 1

        logger.info(f"Batch completed. Success: {success_count}/{len(links)}")

    async def cleanup(self):
        if self.browser_manager:
            await self.browser_manager.close()
            logger.info("Resources released.")
