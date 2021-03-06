import os
import utils
import numpy as np

from xml.etree import ElementTree
from keras.utils import Sequence
from skimage import io, transform
from sklearn.model_selection import StratifiedShuffleSplit, train_test_split


def _fetch_attrs(element, attrs, default_value='0', apply_fn=lambda x: int(x)):
    # Some elements are missing attributes.
    if type(attrs) is list:
        return [apply_fn(element.attrib.get(attr) or default_value) for attr in attrs]
    return apply_fn(element.attrib.get(attrs) or default_value)


def _parse_xml(xml):
    root = ElementTree.parse(xml).getroot()
    data = []
    for space in root.findall('space'):
        rect, contour = space.getchildren()
        data.append({
            'id': _fetch_attrs(space, 'id'),
            'occupied': _fetch_attrs(space, 'occupied'),
            'center': _fetch_attrs(rect.getchildren()[0], ['x', 'y']),
            'size': _fetch_attrs(rect.getchildren()[1], ['w', 'h']),
            'angle': _fetch_attrs(rect.getchildren()[2], 'd'),
            'bb': [_fetch_attrs(p, ['x', 'y']) for p in contour.getchildren()]
        })
    return data


def _cleanup(dir):
    # These have no corresponding xml
    bad_files = ['PUCPR/Sunny/2012-11-06/2012-11-06_18_48_46.jpg']
    for f in bad_files:
        f = os.path.join(dir, f)
        if os.path.exists(f):
            os.remove(f)


def generate_variant(fname):
    lot_weather = fname.split('/')[-4:-2]
    return '_'.join(lot_weather)


class Dataset(object):

    def __init__(self, base_dir='../data'):
        self._base_dir = base_dir
        self._dir = os.path.join(base_dir, 'PKLot')
        _cleanup(self._dir)

        self.X = np.array(utils.recursive_glob(self._dir, "*.jpg"))
        self.y = np.array([s[:-3] + 'xml' for s in self.X])
        shuffled_indices = np.arange(len(self.X))
        np.random.shuffle(shuffled_indices)
        self.X = self.X[shuffled_indices]
        self.y = self.y[shuffled_indices]

        self.variant = np.array([generate_variant(s) for s in self.X])
        self._test_indices = None
        self._train_indices = None

    @property
    def test_indices(self):
        if self._test_indices is None:
            save_path = os.path.join(self._base_dir, 'test_indices.npy')
            if os.path.exists(save_path):
                self._test_indices = np.load(save_path)
                self._train_indices = np.setdiff1d(np.arange(0, len(self.X)), self._test_indices)
            else:
                sss = StratifiedShuffleSplit(n_splits=1, test_size=0.1)
                self._train_indices, self._test_indices = next(sss.split(np.zeros(len(self.variant)), self.variant))
                np.save(save_path, self._test_indices)
        return self._test_indices

    def train_val_split(self, val_size=0.1):
        # Ensure train/test split.
        _ = self.test_indices

        return train_test_split(self.X[self._train_indices], self.y[self._train_indices],
                                test_size=val_size,
                                stratify=self.variant[self._train_indices])

    def get_test_data(self):
        return self.X[self.test_indices], self.y[self.test_indices]


class DataLoader(Sequence):

        def __init__(self, X, y, img_width=320, img_height=180, batch_size=32):
            self.X = X
            self.y = y
            self.img_width = img_width
            self.img_height = img_height
            self.batch_size = batch_size

        def __len__(self):
            return len(self.X) // self.batch_size

        def __getitem__(self, batch_idx):
            X = self.X[batch_idx * self.batch_size: (batch_idx + 1) * self.batch_size]
            y = self.y[batch_idx * self.batch_size: (batch_idx + 1) * self.batch_size]

            batch_x = np.zeros(shape=(len(X), self.img_height, self.img_width, 3), dtype=np.float32)
            batch_y = np.zeros(shape=len(X), dtype=np.float32)

            for i in range(len(X)):
                batch_x[i] = transform.resize(io.imread(X[i]),
                                              output_shape=(self.img_height, self.img_width),
                                              preserve_range=True).astype('uint8')
                batch_y[i] = sum(data['occupied'] for data in _parse_xml(y[i]))

            return utils.center(batch_x), batch_y


if __name__ == '__main__':
    ds = Dataset()
    ds.train_val_split()
