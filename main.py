import argparse
import sys
import os
import yaml
from core.parser import SmartParser
from core.renderer import Renderer
from core.ai_client import AIClient

def load_config(config_path='config.yaml'):
    # Determine absolute path to config.yaml which is in the same dir as main.py
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, config_path)
    
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    return {}

def main():
    parser = argparse.ArgumentParser(description="PosterGen: Convert Markdown to Social Media Slides")
    parser.add_argument("input_file", help="Path to input Markdown file")
    parser.add_argument("--mode", choices=['split', 'ai'], default='split', help="Processing mode (split: Smart Pagination, ai: AI Refactoring)")
    parser.add_argument("--theme", default='default', help="Theme name (folder in themes/)")
    parser.add_argument("--prompt", help="Path to custom prompt file (only for AI mode)")
    parser.add_argument("--output", help="Output directory override")
    
    args = parser.parse_args()
    
    config = load_config()
    
    # Override config with args
    if args.output:
        config['output_dir'] = args.output
    
    # Check input
    if not os.path.exists(args.input_file):
        print(f"Error: Input file '{args.input_file}' not found.")
        sys.exit(1)
        
    with open(args.input_file, 'r', encoding='utf-8') as f:
        markdown_text = f.read()

    slides_data = []

    if args.mode == 'split':
        print("[Mode] Smart Pagination (Split)")
        parser_tool = SmartParser(config)
        slides_data = parser_tool.parse(markdown_text)
    
    elif args.mode == 'ai':
        print("[Mode] AI Refactoring")
        client = AIClient(config)
        slides_data = client.generate_slides(markdown_text, args.prompt)

    if not slides_data:
        print("Error: No slides generated.")
        sys.exit(1)

    # Render
    renderer = Renderer(config)
    
    # 1. HTML Preview
    html_path = renderer.render_html(slides_data, args.theme)
    
    # 2. Screenshot
    renderer.run_screenshot_task(html_path)

if __name__ == "__main__":
    main()
