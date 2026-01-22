import re
import markdown
import requests
from PIL import Image
import io
import os
import hashlib

class SmartParser:
    def __init__(self, config):
        self.config = config
        # Heuristic constants for height estimation (virtual units)
        # Total available height per slide (excluding header/footer)
        # Reduced to 440 to strictly prevent footer overflow
        # Total available height per slide (excluding header/footer)
        # Final reduction to 420 to accommodate all block types safely
        self.MAX_HEIGHT = 420
        
        # Ensure cache directory exists
        self.cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cache', 'images')
        os.makedirs(self.cache_dir, exist_ok=True)
        
    def _get_image_height(self, url):
        """
        Downloads image (with caching) and calculates render height.
        Max height constrained to 380px to match CSS.
        """
        try:
            # Generate cache filename
            url_hash = hashlib.md5(url.encode()).hexdigest()
            ext = os.path.splitext(url)[1] or '.png'
            cache_path = os.path.join(self.cache_dir, f"{url_hash}{ext}")
            
            # Download if not cached
            if not os.path.exists(cache_path):
                print(f"Downloading image: {url}")
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                with open(cache_path, 'wb') as f:
                    f.write(response.content)
            else:
                print(f"Using cached image: {cache_path}")
                
            # Open with PIL to get dimensions
            with Image.open(cache_path) as img:
                width, height = img.size
                aspect_ratio = width / height
                
                # Container width is fixed (Slide 375px - 50px padding = 325px)
                # But actual image-wrapper constraint might vary.
                # Assuming full width usage:
                render_width = 325
                calc_height = render_width / aspect_ratio
                
                # Apply hard constraints
                # Increased to 520 to allow full-slide vertical images
                final_height = min(calc_height, 520)
                print(f"Image calculated height: {final_height:.1f} (Original: {width}x{height})")
                return final_height
        except Exception as e:
            print(f"Error processing image {url}: {e}")
            return 300 # Fallback safe height 
        
    def parse(self, markdown_text):
        """
        Parses markdown text into a list of Slide objects using Smart Pagination.
        """
        blocks = self._tokenize(markdown_text)
        slides = self._paginate(blocks)
        return slides

    def _tokenize(self, text):
        """
        Splits text into content blocks (Headers, Paragraphs, Lists).
        Returns list of dict: {'type': 'p|h2|list|code', 'content': '...', 'html': '...'}
        """
        lines = text.strip().split('\n')
        blocks = []
        current_block = []
        current_type = 'p'

        def flush_block():
            nonlocal current_block, current_type
            if current_block:
                content = '\n'.join(current_block).strip()
                if content:
                    blocks.append(self._create_block(current_type, content))
                current_block = []

        for line in lines:
            line = line.rstrip()
            stripped_line = line.strip()

            # 1. Handle Code Block Transitions & Content
            if stripped_line.startswith('```'):
                if current_type == 'code':
                    # End of code block
                    current_block.append(line)
                    flush_block()
                    current_type = 'p'
                else:
                    # Start of code block
                    flush_block() # Flush previous paragraph
                    current_type = 'code'
                    current_block.append(line)
                continue
            
            # If inside code block, capture everything (ignore headers/lists)
            if current_type == 'code':
                current_block.append(line)
                continue

            # 2. Detect Headers (Only if not in code)
            if line.startswith('#'):
                flush_block()
                level = len(line.split(' ')[0])
                if level == 1:
                    current_type = 'h1' 
                elif level == 2:
                    current_type = 'h2'
                else:
                    current_type = 'h3'
                current_block.append(line.lstrip('#').strip())
                flush_block()
                current_type = 'p' 
                continue
            
            # 3. Detect List Items
            if stripped_line.startswith('- ') or stripped_line.startswith('* ') or re.match(r'^\d+\.', stripped_line):
                if current_type != 'list':
                    flush_block()
                    current_type = 'list'
                current_block.append(line)
                continue
            
            # 4. Detect Images
            # Matches ![alt](url)
            if re.match(r'!\[.*?\]\(.*?\)', stripped_line):
                flush_block()
                current_type = 'image'
                current_block.append(stripped_line)
                flush_block() # Images are standalone blocks
                current_type = 'p'
                continue

            # 5. Detect Empty Lines
            if not stripped_line:
                flush_block()
                current_type = 'p'
                continue

            # 5. Normal Text
            current_block.append(line)

        flush_block()
        return blocks

    def _create_block(self, type, content):
        # Format HTML content based on type
        html = ""
        # Helper to process inline markdown (stripping <p> tags)
        def process_inline(text):
            m = markdown.markdown(text)
            if m.startswith('<p>') and m.endswith('</p>'):
                return m[3:-4]
            return m

        if type == 'h2':
            html = f"<h2>{process_inline(content)}</h2>"
        elif type == 'h3':
            html = f"<h3>{process_inline(content)}</h3>"
        elif type == 'list':
            html = markdown.markdown(content)
        elif type == 'code':
            # Remove backticks and language
            clean_content = re.sub(r'^```\w*\n?|```$', '', content, flags=re.MULTILINE).strip()
            html = f'<div class="code-block">{clean_content}</div>'
        elif type == 'image':
            # Extract URL and Alt
            match = re.search(r'!\[(.*?)\]\((.*?)\)', content)
            if match:
                alt, url = match.groups()
                html = f'<div class="image-wrapper"><img src="{url}" alt="{alt}"></div>'
        else:
            # Paragraph
            # Check for Blockquote
            if content.startswith('>'):
                 html = markdown.markdown(content)
                 # Blockquotes usually narrower (more lines) + margins
                 lines = len(content) / 18 # More wrapping due to indentation
                 height = lines * 24 + 50 
                 return {'type': 'blockquote', 'content': content, 'html': html, 'height': height}

            # Check if it looks like a "Card" (e.g. bold title at start)
            # Naive bold detection: **Title** Content
            # match = re.match(r'\*\*(.*?)\*\*(.*)', content)
            # if match:
            #     title, body = match.groups()
            #     # If body is substantial or contains update keywords, treat as Card
            #     body_html = markdown.markdown(body.strip())
            #     html = f'<div class="card"><h3>{title}</h3>{body_html}</div>'
            # else:
            html = markdown.markdown(content)
        
        # Estimate height
        height = 0
        if type == 'h2': height = 60 # Increased spacing
        elif type == 'h3': height = 50
        elif type == 'list': 
            # Complex estimation: Iterate items to account for wrapping
            items = content.split('\n')
            total_visual_lines = 0
            for item in items:
                # Remove markdown bullets/numbers for cleaner char count
                clean_text = re.sub(r'^(\s*[-*]|\s*\d+\.)\s*', '', item)
                # List has indent, so effective width is smaller (use 20 chars/line)
                item_lines = max(1, len(clean_text) / 20)
                total_visual_lines += item_lines
            
            # Height = Lines * LineHeight + (ItemCount * ItemSpacing) + BlockPadding
            height = total_visual_lines * 24 + len(items) * 8 + 10
        elif type == 'code': height = len(content.split('\n')) * 30 + 30 # Reduced from 40 to 30

        elif type == 'image': 
            # Extract URL for dynamic calculation
            match = re.search(r'!\[.*?\]\((.*?)\)', content)
            if match:
                url = match.group(1)
                height = self._get_image_height(url)
            else:
                height = 300 # Fallback

        elif 'card' in html: 
            # Chinese characters are wider/denser, but line-height is 1.6
            # Approx 25 chars per line at 14px size.
            lines = len(content) / 20 # Conservative estimate for wrapping
            height = lines * 24 + 80 # Increased base padding/margin for cards
        else: 
            # Paragraph
            lines = len(content) / 22 # Conservative estimate
            height = lines * 24 + 20 # Reduced base margin from 30 to 20 for 10px Layout

        return {'type': type, 'content': content, 'html': html, 'height': height}

    def _try_split_list(self, block, available_height):
        """
        Attempts to split a list block into two parts.
        Part 1 fits in available_height.
        Part 2 is the remainder.
        Returns (block1, block2) or (None, None) if split not possible/worthwhile.
        """
        content = block['content']
        items = content.split('\n')
        
        # Calculate per-item heights
        item_heights = []
        for item in items:
            clean_text = re.sub(r'^(\s*[-*]|\s*\d+\.)\s*', '', item)
            item_lines = max(1, len(clean_text) / 20)
            h = item_lines * 24 + 8 # 24px line + 8px spacing
            item_heights.append(h)
            
        # Base padding for the list block (top/bottom)
        base_padding = 10
        
        current_h = base_padding
        split_index = -1
        
        for i, h in enumerate(item_heights):
            if current_h + h > available_height:
                break
            current_h += h
            split_index = i
            
        # "Sticky Parent" Logic: 
        # If split_index falls on a sub-item (indented), backtrack to its parent.
        if split_index > 0:
            # Check indentation of the item we are about to include as the LAST item of part1
            # Actually, `split_index` is the index of the *last item that fits*.
            # The *next* item (at split_index + 1) is what gets pushed to next page.
            # But the requirement is: don't break a group. 
            # Strategy: If we are cutting *after* a parent (so children go to next page), that's bad? 
            # - Parent on Page 1, Children on Page 2 -> Bad (Orphan Parent)
            # - Parent + Child 1 on Page 1, Child 2 on Page 2 -> Bad (Broken Sublist)
            
            # Simplified Strategy: Find the indentation of the item *at* split_index.
            # If it has indentation, backtrack until we find an item with *less* indentation.
            # That item is likely the parent. We should exclude it from Part 1 so it moves to Part 2 with its children.
            
            curr_indent = len(items[split_index]) - len(items[split_index].lstrip())
            
            # Backtrack to find start of this group (parent)
            temp_index = split_index
            while temp_index >= 0:
                indent = len(items[temp_index]) - len(items[temp_index].lstrip())
                if indent < curr_indent:
                    # Found the parent! 
                    # We want to move the Parent to Part 2 strictly.
                    # So split_index should be one *before* text_index.
                    # BUT we must verify we aren't moving *everything* to Part 2 (result empty Part 1).
                    if temp_index > 0:
                        split_index = temp_index - 1
                    break
                temp_index -= 1
        
        # If we couldn't fit even one item, or if we fit all (shouldn't happen if overflow triggered), return None
        if split_index < 0:
            return None, None
        
        # Create two new blocks
        part1_items = items[:split_index+1]
        part2_items = items[split_index+1:]
        
        if not part1_items or not part2_items:
            return None, None
            
        import textwrap
        # Part 2 needs to ideally be dedented so it renders as a fresh list, 
        # unless user wants to preserve hierarchy (hard to do without parent).
        # We'll dedent to ensure it doesn't become a code block.
        part2_text = '\n'.join(part2_items)
        part2_dedented = textwrap.dedent(part2_text)
        
        block1 = self._create_block('list', '\n'.join(part1_items))
        block2 = self._create_block('list', part2_dedented)
        
        return block1, block2

    def _paginate(self, blocks):
        slides = []
        current_slide_content = []
        current_height = 0
        
        # Slide 1 is always cover if H1 exists
        cover_block = next((b for b in blocks if b['type'] == 'h1'), None)
        blocks = [b for b in blocks if b['type'] != 'h1'] # Remove H1 from flow
        
        if cover_block:
            slides.append({
                'is_cover': True,
                'cover_title': cover_block['content'],
                'cover_subtitle': "Generated by PosterGen", # Placeholder
                'tagline': "PARENT PROCESS",
                'header_left': "PARENT PROCESS",
                'header_right': "COVER",
                'footer_left': "AUTHOR",
                'footer_right': "SLIDE 01"
            })

        slide_index = 2 if cover_block else 1

        # Use a queue for blocks to allow dynamic insertion of split blocks
        import collections
        block_queue = collections.deque(blocks)
        
        # Log setup
        output_dir = self.config.get('output_dir', 'output')
        os.makedirs(output_dir, exist_ok=True)
        log_path = os.path.join(output_dir, 'layout.log')

        with open(log_path, 'w', encoding='utf-8') as log_file:
            log_file.write(f"=== Layout Debug Log ===\nMAX_HEIGHT: {self.MAX_HEIGHT}\n\n")
            
            while block_queue:
                block = block_queue.popleft()
                
                # Orphan Header Protection
                if block['type'] in ['h2', 'h3']:
                    if block_queue:
                        next_blk = block_queue[0]
                        if current_height + block['height'] + next_blk['height'] > self.MAX_HEIGHT and current_slide_content:
                             msg = f"[Slide {slide_index}] [PROTECTION] Moving orphan content next slide (Req: {current_height + block['height'] + next_blk['height']:.1f})\n"
                             # print(msg.strip())  <-- Removed console output
                             log_file.write(msg)
                             
                             slides.append(self._finalize_slide(current_slide_content, slide_index))
                             slide_index += 1
                             current_slide_content = []
                             current_height = 0

                # Content Snippet for log
                snippet = block['content'].replace('\n', ' ')[:30] + "..." if len(block['content']) > 30 else block['content'].replace('\n', ' ')
                
                # DEBUG LOGGING
                log_msg = f"[Slide {slide_index:02d}] Type: {block['type']:<5} | H: {block['height']:<5.1f} | CurH: {current_height:<5.1f} -> {current_height + block['height']:<5.1f} / {self.MAX_HEIGHT} | Content: {snippet}\n"
                # print(log_msg.strip()) <-- Removed console output
                log_file.write(log_msg)
                
                if current_height + block['height'] > self.MAX_HEIGHT and current_slide_content:
                    log_file.write(f"---> NEW SLIDE (Overflow: {current_height + block['height']:.1f} > {self.MAX_HEIGHT})\n")
                    # Flush current slide
                    slides.append(self._finalize_slide(current_slide_content, slide_index))
                    slide_index += 1
                    current_slide_content = []
                    current_height = 0
                
                current_slide_content.append(block['html'])
                current_height += block['height']

        # Flush last slide
        if current_slide_content:
            slides.append(self._finalize_slide(current_slide_content, slide_index))

        # Update total count
        total_slides = len(slides)
        for i, slide in enumerate(slides):
            slide['footer_right'] = f"SLIDE {i+1:02d}/{total_slides:02d}"

        return slides

    def _finalize_slide(self, content_list, index):
        return {
            'is_cover': False,
            'header_left': "PARENT PROCESS",
            'header_right': "CONTENT",
            'footer_left': "POSTER GEN",
            'footer_right': f"SLIDE {index:02d}",
            'content': '\n'.join(content_list)
        }
