#!/usr/bin/env python3

import argparse
import asyncio
import json
import os
import logging
from datetime import datetime
from urllib.parse import quote
import socket
import sys

from aiohttp import web

from openpilot.common.params import Params
from openpilot.system.hardware import PC, TICI

try:
    # Add bundled zeroconf library
    zeroconf_path = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), "python-zeroconf/src"))
    if not os.path.isdir(zeroconf_path):
        logging.critical(f"Zeroconf library not found at: {zeroconf_path}")
        sys.exit(1)
    sys.path.insert(0, zeroconf_path)
    from zeroconf.asyncio import AsyncZeroconf as Zeroconf, AsyncServiceInfo as ServiceInfo
except ImportError:
    logging.critical("Failed to import a required library. Make sure submodules are present and updated.")
    sys.exit(1)


# --- Zeroconf Service Broadcast Settings ---
zeroconf_instance = None
service_info = None
current_ip_address = None

# --- File Browser Settings ---
DEFAULT_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), '..') if PC else '/data/media/0/realdata')
WEB_DIST_PATH = os.path.join(os.path.dirname(__file__), "..", "web", "dist")

def get_safe_path(requested_path):
    """Ensures the requested path is within DEFAULT_DIR, preventing arbitrary file access"""
    combined_path = os.path.join(DEFAULT_DIR, requested_path.lstrip('/'))
    safe_path = os.path.realpath(combined_path)
    if os.path.commonpath((safe_path, DEFAULT_DIR)) == DEFAULT_DIR:
        return safe_path
    return None

async def list_files_api(request):
    """API endpoint to list files and folders"""
    try:
        path_param = request.query.get('path', '/')
        safe_path = get_safe_path(path_param)
        if not safe_path or not os.path.isdir(safe_path):
            return web.json_response({'error': 'Invalid or Not Found Path'}, status=404)
        items = []
        for entry in os.listdir(safe_path):
            full_path = os.path.join(safe_path, entry)
            try:
                stat = os.stat(full_path)
                is_dir = os.path.isdir(full_path)
                items.append({
                    'name': entry,
                    'is_dir': is_dir,
                    'mtime': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
                    'size': stat.st_size if not is_dir else 0
                })
            except FileNotFoundError:
                continue
        directories = sorted([item for item in items if item['is_dir']], key=lambda x: x['mtime'], reverse=True)
        files = sorted([item for item in items if not item['is_dir']], key=lambda x: x['mtime'], reverse=True)
        items = directories + files
        relative_path = os.path.relpath(safe_path, DEFAULT_DIR)
        if relative_path == '.':
            relative_path = ''
        return web.json_response({'path': relative_path, 'files': items})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

async def serve_player_api(request):
    """API endpoint to serve the HLS player page"""
    file_path = request.query.get('file')
    if not file_path:
        return web.Response(text="File parameter is required.", status=400)

    player_html_path = os.path.join(WEB_DIST_PATH, 'pages', 'player.html')
    try:
        with open(player_html_path, 'r') as f:
            html_template = f.read()
    except FileNotFoundError:
        return web.Response(text="Player HTML not found.", status=500)

    encoded_path = quote(file_path)
    html = html_template.replace('{{FILE_PATH}}', encoded_path)
    return web.Response(text=html, content_type='text/html')

async def serve_manifest_api(request):
    """API endpoint to dynamically generate m3u8 playlist"""
    file_path = request.query.get('file').lstrip('/')
    if not file_path:
        return web.Response(text="File parameter is required.", status=400)
    encoded_path = quote(file_path)
    manifest = f"""#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:60\n#EXT-X-PLAYLIST-TYPE:VOD\n#EXTINF:60.0,\n/media/{encoded_path}\n#EXT-X-ENDLIST\n"""
    return web.Response(text=manifest, content_type='application/vnd.apple.mpegurl')

async def save_settings_api(request):
    """API endpoint to receive and save settings"""
    try:
        data = await request.json()
        logging.getLogger("web_ui").info(f"Received settings to save: {data}")
        return web.json_response({'status': 'success', 'message': 'Settings saved successfully!'})
    except Exception as e:
        logging.getLogger("web_ui").error(f"Error saving settings: {e}")
        return web.json_response({'status': 'error', 'message': str(e)}, status=500)

async def init_api(request):
    """API endpoint to provide initial data to the client."""
    try:
        params = Params()
        is_metric = params.get_bool("IsMetric")
        dp_dev_dashy = int(params.get("dp_dev_dashy") or 0)
        return web.json_response({'is_metric': is_metric, 'dp_dev_dashy': dp_dev_dashy})
    except Exception as e:
        logging.getLogger("web_ui").error(f"Error fetching initial data: {e}")
        return web.json_response({}, status=500)

def get_ip():
    """Attempts to get the local LAN IP address by connecting to an external address"""
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
        return ip
    except Exception:
        ip = None
    finally:
        if s:
            s.close()
    return ip

async def register_zeroconf_service(ip_address, port):
    """Registers the zeroconf service with the given IP address and port."""
    global service_info, zeroconf_instance
    if not ip_address or not zeroconf_instance:
        return

    server_name = f"dashy-{socket.gethostname()}.local."
    service_info = ServiceInfo(
        "_http._tcp.local.",
        f"dashy._http._tcp.local.",
        addresses=[socket.inet_aton(ip_address)],
        port=port,
        properties={"version": "1.0", "path": "/"},
        server=server_name,
    )
    logging.getLogger("web_ui").info(f"Registering Zeroconf service: {service_info.name} Address: {ip_address}:{port}")
    await zeroconf_instance.async_register_service(service_info)

async def unregister_zeroconf_service():
    """Unregisters the zeroconf service."""
    global service_info, zeroconf_instance
    if service_info and zeroconf_instance:
        logging.getLogger("web_ui").info(f"Unregistering old Zeroconf service at {current_ip_address}")
        try:
            await zeroconf_instance.async_unregister_service(service_info)
        except Exception as e:
            logging.getLogger("web_ui").warning(f"Error unregistering service: {e}")
        service_info = None

async def monitor_ip_address_changes(port: int):
    global zeroconf_instance, service_info, current_ip_address
    while True:
        await asyncio.sleep(10)
        new_ip_address = get_ip()

        if new_ip_address != current_ip_address:
            logging.getLogger("web_ui").info(f"IP address changed. Old: {current_ip_address}, New: {new_ip_address}")

            if zeroconf_instance:
                if service_info:
                    await unregister_zeroconf_service()
                await zeroconf_instance.async_close()
                zeroconf_instance = None

            current_ip_address = new_ip_address

            if current_ip_address is not None:
                zeroconf_instance = Zeroconf()
                await register_zeroconf_service(current_ip_address, port)
            else:
                logging.getLogger("web_ui").warning("No valid LAN IP found, Zeroconf service not started.")

async def on_startup(app):
    global zeroconf_instance, current_ip_address
    port = app['port']
    logging.getLogger("web_ui").info("Web UI application starting up...")
    current_ip_address = get_ip()
    if current_ip_address:
        zeroconf_instance = Zeroconf()
        await register_zeroconf_service(current_ip_address, port)
    else:
        logging.getLogger("web_ui").warning("No valid LAN IP found, Zeroconf service not started.")
        zeroconf_instance = None
    app['ip_monitor_task'] = asyncio.create_task(monitor_ip_address_changes(port))

async def on_cleanup(app):
    global zeroconf_instance
    logging.getLogger("web_ui").info("Web UI application shutting down...")
    if 'ip_monitor_task' in app and not app['ip_monitor_task'].done():
        app['ip_monitor_task'].cancel()
        try:
            await app['ip_monitor_task']
        except asyncio.CancelledError:
            logging.getLogger("web_ui").info("IP monitor task cancelled successfully.")
    if zeroconf_instance:
        logging.getLogger("web_ui").info("Closing final Zeroconf instance.")
        await zeroconf_instance.async_close()
        zeroconf_instance = None

# --- CORS Middleware ---
@web.middleware
async def cors_middleware(request, handler):
    response = await handler(request)
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

async def handle_cors_preflight(request):
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            'Access-Control-Max-Age': '86400',
        }
        return web.Response(status=200, headers=headers)
    return await request.app['handler'](request)

def setup_aiohttp_app(host: str, port: int, debug: bool):
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logging.getLogger("web_ui").setLevel(logging.DEBUG if debug else logging.INFO)

    app = web.Application(middlewares=[cors_middleware])
    app['port'] = port

    # Register API endpoints
    app.router.add_get("/api/init", init_api)
    app.router.add_get("/api/files", list_files_api)
    app.router.add_get("/api/play", serve_player_api)
    app.router.add_get("/api/manifest.m3u8", serve_manifest_api)
    # app.router.add_post("/api/settings", save_settings_api)

    # Static files
    app.router.add_static('/media', path=DEFAULT_DIR, name='media', show_index=False, follow_symlinks=False)
    app.router.add_static('/download', path=DEFAULT_DIR, name='download', show_index=False, follow_symlinks=False)
    app.router.add_get("/", lambda r: web.FileResponse(os.path.join(WEB_DIST_PATH, "index.html")))
    app.router.add_static("/", path=WEB_DIST_PATH)

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    # Add CORS preflight handler
    app.router.add_route('OPTIONS', '/{tail:.*}', handle_cors_preflight)

    return app

def main():
    # rick - may need "sudo ufw allow 5088" to allow port access
    parser = argparse.ArgumentParser(description="Openpilot Web UI Server")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to listen on")
    parser.add_argument("--port", type=int, default=5088, help="Port to listen on")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    app = setup_aiohttp_app(args.host, args.port, args.debug)
    web.run_app(app, host=args.host, port=args.port)

if __name__ == "__main__":
    main()
