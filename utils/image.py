"""
utils/image.py
Image handling utilities - download, validate, and process images from Discord.
"""

import logging
import asyncio
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

import aiohttp
from PIL import Image

log = logging.getLogger("roselinne.image")


class ImageHandler:
    """Handle image downloading and validation."""

    MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20MB
    SUPPORTED_FORMATS = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    IMAGE_TIMEOUT = aiohttp.ClientTimeout(total=30)

    @staticmethod
    async def download_image(url: str) -> Optional[bytes]:
        """
        Download image from URL (e.g., Discord CDN).
        Returns image bytes or None if failed.
        """
        try:
            async with aiohttp.ClientSession(timeout=ImageHandler.IMAGE_TIMEOUT) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        log.warning(f"Failed to download image: HTTP {resp.status}")
                        return None

                    content_type = resp.headers.get("content-type", "").lower().split(";", 1)[0]
                    if content_type not in ImageHandler.SUPPORTED_FORMATS:
                        log.warning(f"Unsupported image format: {content_type}")
                        return None

                    size = int(resp.headers.get("content-length", 0))
                    if size > ImageHandler.MAX_IMAGE_SIZE:
                        log.warning(f"Image too large: {size} bytes")
                        return None

                    image_data = await resp.read()
                    
                    if len(image_data) > ImageHandler.MAX_IMAGE_SIZE:
                        log.warning(f"Downloaded image exceeds size limit")
                        return None

                    return image_data

        except asyncio.TimeoutError:
            log.warning("Image download timed out")
            return None
        except Exception as e:
            log.error(f"Error downloading image: {e}")
            return None

    @staticmethod
    def validate_image(image_data: bytes) -> bool:
        """Check if image data is valid."""
        try:
            img = Image.open(BytesIO(image_data))
            img.verify()
            return True
        except Exception as e:
            log.warning(f"Invalid image data: {e}")
            return False

    @staticmethod
    def get_image_info(image_data: bytes) -> Optional[Tuple[str, int, int]]:
        """
        Get image format, width, and height.
        Returns (format, width, height) or None if invalid.
        """
        try:
            img = Image.open(BytesIO(image_data))
            return (img.format or "UNKNOWN", img.width, img.height)
        except Exception as e:
            log.warning(f"Could not get image info: {e}")
            return None

    @staticmethod
    def compress_image(image_data: bytes, max_width: int = 1024) -> bytes:
        """
        Compress image for faster processing.
        Reduces quality and size while maintaining aspect ratio.
        """
        try:
            img = Image.open(BytesIO(image_data))
            
            # Scale down if too large
            if img.width > max_width:
                ratio = max_width / img.width
                new_height = int(img.height * ratio)
                img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
            
            # Convert to RGB if necessary (remove alpha channel)
            if img.mode in ("RGBA", "LA", "P"):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                img = bg

            # Save as JPEG with compression
            output = BytesIO()
            img.save(output, format="JPEG", quality=75, optimize=True)
            return output.getvalue()

        except Exception as e:
            log.warning(f"Could not compress image: {e}")
            return image_data
