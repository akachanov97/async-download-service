"""
MIT License

Copyright (c) 2021 akachanov97

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

"""

import os
import logging
import asyncio
import argparse
import aiofiles
import aiohttp.web

# Make delay between sending of chunks
SLOWDOWN = bool(os.getenv("SLOWDOWN", False))
# Time to delay in seconds
TIME2DELAY = 1

# Size of chunks in bytes
CHUNK_SIZE = 256*1024

# Directory to storing files
MEDIA_DIR = os.getenv("MEDIA_DIR", 'test_photos')

# Log messages level
LOG_LVL = int(os.getenv("LOGGING", logging.ERROR))


def _exists(files_folder: str) -> bool:
    """Check if directory exists

    Args:
        files_folder (str): Folder for downloading

    Returns:
        bool: True if folder is exists else False
    """

    path = os.path.join(MEDIA_DIR, files_folder)
    return os.path.isdir(path)


def _response_header(file_name: str) -> aiohttp.web.StreamResponse:
    """Creating response header

    Args:
        file_name (str): Name of downloaded file

    Returns:
        StreamResponse: StreamResponse object
    """

    response = aiohttp.web.StreamResponse()
    response.headers['Content-Type'] = 'application/zip'
    response.headers['Content-Disposition'] = \
        f'attachment; filename="{file_name}.zip"'

    return response


async def archivate(request: aiohttp.web.Request) -> None:
    """Archivate and send archive by chunks

    Args:
        request (Request): HTTP Request

    Raises:
        aiohttp.web.HTTPBadRequest: raise if 'archive_hash'
                                    was not passed in the request
        aiohttp.web.HTTPNotFound: raise if folder with 'archive_hash'
                                  name was not found
    """

    archive_hash = request.match_info.get('archive_hash')
    if not archive_hash:
        raise aiohttp.web.HTTPBadRequest()

    if not _exists(archive_hash):
        raise aiohttp.web.HTTPNotFound(
            text="Archive not exists or was deleted!")

    response = _response_header(archive_hash)
    await response.prepare(request)

    args = ['zip', '-r', '-', archive_hash]
    zip_process = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, cwd=MEDIA_DIR)

    try:
        while True:
            if zip_process.stdout.at_eof():
                break
            chunk = await zip_process.stdout.read(CHUNK_SIZE)
            logging.debug(u'Sending archive chunk ...')
            await response.write(chunk)

            if SLOWDOWN:
                await asyncio.sleep(TIME2DELAY)

        await response.write_eof()
    except:
        # Перехватываю ВСЕ exception'ы, включая BaseException,
        # чтобы остановить работу zip

        logging.info(u'Download was interrupted')
        zip_process.kill()
        raise

    finally:
        await zip_process.wait()


async def handle_index_page(
        request: aiohttp.web.Request) -> aiohttp.web.Response:
    """Handler of main page

    Args:
        request (Request): HTTP Request

    Returns:
        [Response]: HTML page as response
    """

    async with aiofiles.open('index.html', mode='r') as index_file:
        index_contents = await index_file.read()
    return aiohttp.web.Response(text=index_contents, content_type='text/html')


def _parse_args():
    """Parse command line arguments

    Returns:
        [Namespace]: Parsed arguments
    """

    parser = argparse.ArgumentParser(
        description='Microservice for streaming files.')
    parser.add_argument('-d', '--debug', choices=['OFF', 'ON'],
                        help='Show logs.'
                             'OFF - show only Errors'
                             'ON - show all logs')
    parser.add_argument('-s', '--slowdown', action='store_true',
                        help='Slow down file downloads')
    parser.add_argument('-m', '--media',
                        help='Change default media directory')

    return parser.parse_args()


def _configure_settings(args):
    """Configure server settings

    Args:
        args ([Namespace]): Parsed command line arguments
    """

    def dbg_lvl(value: str) -> int:
        """Set log messages level

        Args:
            value (str): ON/OFF value

        Returns:
            int: log messages level from logging module
        """
        _map = {
            'ON': logging.NOTSET,
            'OFF': logging.ERROR,
        }

        if not value:
            # Если не задано,
            # возвращаем значение по умолчанию
            return LOG_LVL

        return _map.get(value, logging.NOTSET)

    global LOG_LVL
    LOG_LVL = dbg_lvl(args.debug)

    # Конструкция "if-else" в данном случае позволит мне
    # применить значение из перенных окружения в случае,
    # если оно не задано в аргументах командной строки

    global SLOWDOWN
    SLOWDOWN = args.slowdown if args.slowdown else SLOWDOWN

    global MEDIA_DIR
    MEDIA_DIR = args.media if args.media else MEDIA_DIR


if __name__ == '__main__':
    args = _parse_args()
    _configure_settings(args)

    logging.basicConfig(level=LOG_LVL)

    app = aiohttp.web.Application()
    app.add_routes([
        aiohttp.web.get('/', handle_index_page),
        aiohttp.web.get('/archive/{archive_hash}/', archivate),
    ])
    aiohttp.web.run_app(app)
