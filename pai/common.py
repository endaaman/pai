from collections import namedtuple, OrderedDict


ORIGINAL_FILENAME = 'org.png'

Result = namedtuple('Result', ['name', 'original', 'overlays'])
Detail = namedtuple('Detail', ['result', 'original_image', 'overlay_images'])

def find_results(results, name):
    for r in results:
        if name == r.name:
            return r
    return None
