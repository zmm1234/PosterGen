from google import genai
import os
import json
import re

class AIClient:
    def __init__(self, config):
        self.api_key = config.get('gemini_api_key')
        self.default_prompt_path = config.get('default_prompt')
        self.client = None
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)

    def generate_slides(self, article_text, prompt_path=None):
        """
        Uses Gemini to refactor article into slides structure.
        """
        if not self.client:
            print("Error: Gemini API Key not configured.")
            return []

        if prompt_path is None:
            prompt_path = self.default_prompt_path
            
        # Resolve prompt path
        if not os.path.isabs(prompt_path):
            base_dir = os.path.dirname(os.path.dirname(__file__))
            prompt_path = os.path.join(base_dir, prompt_path)

        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                system_prompt = f.read()
        except FileNotFoundError:
            print(f"Error: Prompt file not found at {prompt_path}")
            return []

        full_prompt = f"{system_prompt}\n\n==========\n文章内容：\n{article_text}\n=========="

        print("[AI] Sending request to Gemini...")
        
        try:
            response = self.client.models.generate_content(
                model='gemini-2.0-flash', 
                contents=full_prompt
            )
            
            # Clean response text (remove ```json ... ``` wrappers)
            text = response.text
            text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
            text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)
            text = text.strip()
            
            # Extract JSON object
            start = text.find('{')
            end = text.rfind('}') + 1
            if start != -1 and end != -1:
                json_str = text[start:end]
                data = json.loads(json_str)
                return self._convert_to_internal_format(data)
            else:
                print("Error: No JSON object found in response.")
                print("Raw Response:", text[:500] + "...")
                return []
                
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON: {e}")
            print("Raw Response:", response.text)
            return []
        except Exception as e:
            print(f"Error calling AI: {e}")
            return []

    def _convert_to_internal_format(self, ai_data):
        """
        Converts AI JSON format to Renderer format.
        AI Format: {slides: [{title, content, visual_cue}]}
        Renderer Format: [{is_cover, title, content...}]
        """
        slides = []
        raw_slides = ai_data.get('slides', [])
        
        # Cover
        if raw_slides:
            cover = raw_slides[0]
            slides.append({
                'is_cover': True,
                'cover_title': cover.get('title', 'Title'),
                'cover_subtitle': cover.get('content', ''),
                'code_block': cover.get('visual_cue', ''),
                'tagline': "AI GENERATED",
                'header_left': "PARENT PROCESS",
                'header_right': "COVER",
                'footer_left': "AI MODE",
                'footer_right': "SLIDE 01"
            })
            
        # Content
        for i, slide in enumerate(raw_slides[1:]):
            content_html = f"<div class='card'><p>{slide['content']}</p></div>"
            if slide.get('visual_cue'):
                content_html += f"<div class='code-block'>{slide['visual_cue']}</div>"
            
            slides.append({
                'is_cover': False,
                'title': slide['title'],
                'content': content_html,
                'header_left': "PARENT PROCESS",
                'header_right': "CONTENT",
                'footer_left': "AI MODE",
                'footer_right': f"SLIDE {i+2:02d}"
            })
            
        # Fix footers
        total = len(slides)
        for i, s in enumerate(slides):
            s['footer_right'] = f"SLIDE {i+1:02d}/{total:02d}"
            
        return slides
