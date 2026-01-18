#!/usr/bin/env python3
"""
Script to generate PWA icons for ResTrack
Creates simple colored icons with 'RT' text in different sizes
"""
import os
from PIL import Image, ImageDraw, ImageFont

def create_icon(size):
    """Create a simple icon with the specified size"""
    # Create a new image with RGBA mode for transparency
    img = Image.new('RGBA', (size, size), (124, 58, 237, 255))  # Purple background
    draw = ImageDraw.Draw(img)

    # Calculate font size based on icon size
    font_size = int(size * 0.4)

    try:
        # Try to use a system font
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        try:
            # Fallback to default font
            font = ImageFont.load_default()
        except:
            font = None

    # Draw white "RT" text in the center
    text = "RT"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (size - text_width) // 2
    y = (size - text_height) // 2

    draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)

    return img

def main():
    """Generate icons in all required sizes"""
    sizes = [72, 96, 128, 144, 192, 512]
    icons_dir = "static/icons"

    # Ensure icons directory exists
    os.makedirs(icons_dir, exist_ok=True)

    for size in sizes:
        icon = create_icon(size)
        filename = f"{icons_dir}/icon-{size}x{size}.png"
        icon.save(filename, "PNG")
        print(f"Generated {filename}")

    print("All icons generated successfully!")

if __name__ == "__main__":
    main()