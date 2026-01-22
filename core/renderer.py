import os
import asyncio
from playwright.async_api import async_playwright
from jinja2 import Environment, FileSystemLoader

class Renderer:
    def __init__(self, config):
        self.config = config
        self.browser_config = config.get('browser', {})
        self.output_dir = config.get('output_dir', 'output')

    def render_html(self, slides_data, theme_name, output_filename='preview.html'):
        """
        Renders the slides data into a single HTML file using Jinja2 templates.
        """
        theme_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'themes', theme_name)
        template_file = 'template.html'
        
        env = Environment(loader=FileSystemLoader(theme_dir))
        template = env.get_template(template_file)
        
        html_content = template.render(slides=slides_data)
        
        # Ensure output directory exists (relative to where script is run, or absolute)
        # We assume output_dir is relative to CWD or absolute.
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            
        output_path = os.path.join(self.output_dir, output_filename)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        print(f"[Renderer] HTML preview saved to: {output_path}")
        return output_path

    async def capture_screenshots(self, html_path):
        """
        Opens the HTML file in Playwright and takes screenshots of each slide.
        """
        print("[Renderer] Starting Playwright to capture screenshots...")
        
        abs_html_path = os.path.abspath(html_path)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            scale_factor = self.browser_config.get('device_scale_factor', 2)
            
            # Create context with high DIP (device scale factor) for Retina quality
            context = await browser.new_context(
                viewport={
                    'width': self.browser_config.get('viewport_width', 1920),
                    'height': self.browser_config.get('viewport_height', 1080)
                },
                device_scale_factor=scale_factor
            )
            
            page = await context.new_page()
            await page.goto(f'file:///{abs_html_path}')
            
            # Locate all slides
            slides = await page.locator('.slide').all()
            print(f"[Renderer] Found {len(slides)} slides to export.")
            
            for i, slide in enumerate(slides):
                index = i + 1
                filename = f"slide_{index:02d}.png"
                filepath = os.path.join(self.output_dir, filename)
                
                # Screenshot the element
                await slide.screenshot(path=filepath, omit_background=False)
                print(f"  -> Saved {filename}")
                
            await browser.close()
            print("[Renderer] All screenshots captured.")

    def run_screenshot_task(self, html_path):
        """Sync wrapper for async task"""
        asyncio.run(self.capture_screenshots(html_path))
