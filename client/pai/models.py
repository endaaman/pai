from collections import namedtuple, OrderedDict

from api import download_image

ResultImageItem = namedtuple('ResultImageItem', ['name', 'path'])
Result = namedtuple('Result', ['name', 'mode', 'original', 'overlays'])

class Detail:
    def __init__(self, result):
        self.result = result
        self.original_image = None
        self.overlay_images = []

    async def download(self):
        self.original_image = await download_image(self.result.original.path)
        for o in self.result.overlays:
            self.overlay_images.append(await download_image(o.path))

def convert_to_results(xx):
    yy = []
    for x in xx:
        r = Result(
            x['name'],
            x['mode'],
            ResultImageItem(**x['original']),
            [ResultImageItem(**r) for r in x['overlays']]
        )
        yy.append(r)
    return yy

def find_results(results, mode, name):
    for r in results:
        if mode == r.mode and name == r.name:
            return r
    return None

