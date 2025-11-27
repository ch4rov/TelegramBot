from .base import base_download

async def download(url: str, custom_opts: dict = None):
    opts = {
        # VK часто отдает HLS потоки (.m3u8), поэтому нужен merge
        'merge_output_format': 'mp4',
    }
    
    if custom_opts:
        opts.update(custom_opts)
        
    return await base_download(url, opts)