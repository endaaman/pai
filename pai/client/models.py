from collections import namedtuple, OrderedDict

Result = namedtuple('Result', ['name', 'original', 'overlays'])
Detail = namedtuple('Detail', ['result', 'original_image', 'overlay_images'])

def find_results(results, mode, name):
    for r in results:
        if mode == r.mode and name == r.name:
            return r
    return None
