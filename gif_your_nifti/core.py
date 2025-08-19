"""Core functions."""

import os
import imageio
import nibabel as nb
import numpy as np
try:
    from matplotlib.cm import get_cmap
except ImportError:
    import matplotlib.pyplot as plt
    get_cmap = plt.get_cmap
from imageio import mimwrite
from skimage.transform import resize
from scipy.ndimage import zoom

def parse_filename(filepath):
    """Parse input file path into directory, basename and extension.

    Parameters
    ----------
    filepath: string
        Input name that will be parsed into directory, basename and extension.

    Returns
    -------
    dirname: str
        File directory.
    basename: str
        File name without directory and extension.
    ext: str
        File extension.

    """
    path = os.path.normpath(filepath)
    dirname = os.path.dirname(path)
    filename = path.split(os.sep)[-1]
    basename, ext = filename.split(os.extsep, 1)
    return dirname, basename, ext


def load_and_prepare_image(filename, size=1):
    """Load and prepare image data.

    Parameters
    ----------
    filename1: str
        Input file (eg. /john/home/image.nii.gz)
    size: float
        Image resizing factor.

    Returns
    -------
    out_img: numpy array

    """
    # Load NIfTI file
    data = nb.load(filename).get_fdata()

    # Pad data array with zeros to make the shape isometric
    maximum = np.max(data.shape)

    out_img = np.zeros([maximum] * 3)

    a, b, c = data.shape
    x, y, z = (list(data.shape) - maximum) / -2

    out_img[int(x):a + int(x),
            int(y):b + int(y),
            int(z):c + int(z)] = data

    out_img *= 255 / out_img.max()  # scale image values between 0-255
    out_img = out_img.astype(np.uint8)  # should be uint8 for PIL

    # Resize image by the following factor
    if size != 1:
        out_img = resize(out_img, [int(size * maximum)] * 3)

    maximum = int(maximum * size)

    return out_img, maximum

def load_and_prepare_image_isotropic(filename, size=1.0, target_spacing=None):
    img = nb.load(filename)
    img = nb.as_closest_canonical(img)  # consistent RAS orientation
    data = img.get_fdata()
    zooms = np.array(img.header.get_zooms()[:3], dtype=float)

    # choose an isotropic spacing to resample to
    if target_spacing is None:
        target_spacing = zooms.min()  # keep highest native resolution
    factors = zooms / float(target_spacing)

    # resample to isotropic voxels
    data_iso = zoom(data, factors, order=1)  # linear is fine for visualization

    # pad to cube then optional global resize
    maximum = int(max(data_iso.shape))
    out_img = np.zeros((maximum, maximum, maximum), dtype=np.float32)
    shape = np.array(data_iso.shape)
    start = ((maximum - shape) // 2).astype(int)
    sx, sy, sz = start
    ex, ey, ez = (start + shape).astype(int)
    out_img[sx:ex, sy:ey, sz:ez] = data_iso

    # scale to 0..255 uint8
    out_img *= 255.0 / out_img.max()
    out_img = out_img.astype(np.uint8)

    if size != 1.0:
        from skimage.transform import resize
        out_img = resize(out_img, [int(size * maximum)] * 3, order=1, preserve_range=True).astype(np.uint8)
        maximum = out_img.shape[0]

    return out_img, maximum

def create_mosaic_normal(out_img, maximum, frameskip):
    """Create grayscale image.

    Parameters
    ----------
    out_img: numpy array
    maximum: int
    frameskip: int

    Returns
    -------
    new_img: numpy array

    """
    new_img = np.array(
        [np.hstack((
            np.hstack((
                np.flip(out_img[i, :, :], 1).T,
                np.flip(out_img[:, maximum - i - 1, :], 1).T)),
            np.flip(out_img[:, :, maximum - i - 1], 1).T))
         for i in range(0,maximum,frameskip)])

    return new_img


def create_mosaic_depth(out_img, maximum, frameskip):
    """Create an image with concurrent slices represented with colors.

    The image shows you in color what the value of the next slice will be. If
    the color is slightly red or blue it means that the value on the next slide
    is brighter or darker, respectifely. It therefore encodes a certain kind of
    depth into the gif.

    Parameters
    ----------
    out_img: numpy array
    maximum: int
    frameskip: int

    Returns
    -------
    new_img: numpy array

    """
    # Load normal mosaic image
    new_img = create_mosaic_normal(out_img, maximum, frameskip)

    # Create RGB image (where red and blue mean a positive or negative shift in
    # the direction of the depicted axis)
    rgb_img = [new_img[i:i + 3, ...] for i in range(maximum - 3)]

    # Make sure to have correct data shape
    out_img = np.rollaxis(np.array(rgb_img), 1, 4)

    # Add the 3 lost images at the end
    out_img = np.vstack(
        (out_img, np.zeros([3] + [o for o in out_img[-1].shape]))).astype(np.uint8)

    return out_img


def create_mosaic_RGB(out_img1, out_img2, out_img3, maximum, frameskip):
    """Create RGB image.

    Parameters
    ----------
    out_img: numpy array
    maximum: int
    frameskip: int

    Returns
    -------
    new_img: numpy array

    """
    # Load normal mosaic image
    new_img1 = create_mosaic_normal(out_img1, maximum, frameskip)
    new_img2 = create_mosaic_normal(out_img2, maximum, frameskip)
    new_img3 = create_mosaic_normal(out_img3, maximum, frameskip)

    # Create RGB image (where red and blue mean a positive or negative shift
    # in the direction of the depicted axis)
    rgb_img = [[new_img1[i, ...], new_img2[i, ...], new_img3[i, ...]]
               for i in range(maximum)]

    # Make sure to have correct data shape
    out_img = np.rollaxis(np.array(rgb_img), 1, 4)

    # Add the 3 lost images at the end
    out_img = np.vstack(
        (out_img, np.zeros([3] + [o for o in out_img[-1].shape])))

    return out_img


def write_gif_normal(filename, size=1, fps=18, frameskip=1):
    """Procedure for writing grayscale image.

    Parameters
    ----------
    filename: str
        Input file (eg. /john/home/image.nii.gz)
    size: float
        Between 0 and 1.
    fps: int
        Frames per second
    frameskip: int
        Will skip frames if >1

    """
    # Load NIfTI and put it in right shape
    out_img, maximum = load_and_prepare_image_isotropic(filename, size)

    # Create output mosaic
    new_img = create_mosaic_normal(out_img, maximum, frameskip)

    # Figure out extension
    ext = '.{}'.format(parse_filename(filename)[2])

    # Write gif file
    mimwrite_(filename.replace(ext, '.gif'), new_img,
             format='gif', fps=int(fps * size))


def write_gif_depth(filename, size=1, fps=18, frameskip=1):
    """Procedure for writing depth image.

    The image shows you in color what the value of the next slice will be. If
    the color is slightly red or blue it means that the value on the next slide
    is brighter or darker, respectifely. It therefore encodes a certain kind of
    depth into the gif.

    Parameters
    ----------
    filename: str
        Input file (eg. /john/home/image.nii.gz)
    size: float
        Between 0 and 1.
    fps: int
        Frames per second
    frameskip: int
        Will skip frames if >1

    """
    # Load NIfTI and put it in right shape
    out_img, maximum = load_and_prepare_image(filename, size)

    # Create output mosaic
    new_img = create_mosaic_depth(out_img, maximum, frameskip)

    # Figure out extension
    ext = '.{}'.format(parse_filename(filename)[2])

    # Write gif file
    mimwrite_(filename.replace(ext, '_depth.gif'), new_img,
             format='gif', fps=int(fps * size))


def write_gif_rgb(filename1, filename2, filename3, size=1, fps=18, frameskip=1):
    """Procedure for writing RGB image.

    Parameters
    ----------
    filename1: str
        Input file for red channel.
    filename2: str
        Input file for green channel.
    filename3: str
        Input file for blue channel.
    size: float
        Between 0 and 1.
    fps: int
        Frames per second
    frameskip: int
        Will skip frames if >1

    """
    # Load NIfTI and put it in right shape
    out_img1, maximum1 = load_and_prepare_image(filename1, size)
    out_img2, maximum2 = load_and_prepare_image(filename2, size)
    out_img3, maximum3 = load_and_prepare_image(filename3, size)

    if maximum1 == maximum2 and maximum1 == maximum3:
        maximum = maximum1

    # Create output mosaic
    new_img = create_mosaic_RGB(out_img1, out_img2, out_img3, maximum, frameskip)

    # Generate output path
    out_filename = '{}_{}_{}_rgb.gif'.format(parse_filename(filename1)[1],
                                             parse_filename(filename2)[1],
                                             parse_filename(filename3)[1])
    out_path = os.path.join(parse_filename(filename1)[0], out_filename)

    # Write gif file
    mimwrite_(out_path, new_img, format='gif', fps=int(fps * size))


def write_gif_pseudocolor(filename, size=1, fps=18, colormap='hot', frameskip=1):
    """Procedure for writing pseudo color image.

    The colormap can be any colormap from matplotlib.

    Parameters
    ----------
    filename1: str
        Input file (eg. /john/home/image.nii.gz)
    size: float
        Between 0 and 1.
    fps: int
        Frames per second
    colormap: str
        Name of the colormap that will be used.
    frameskip: int
        Will skip frames if >1

    """
    # Load NIfTI and put it in right shape
    out_img, maximum = load_and_prepare_image(filename, size)

    # Create output mosaic
    new_img = create_mosaic_normal(out_img, maximum, frameskip)

    # Transform values according to the color map
    cmap = get_cmap(colormap)
    color_transformed = [cmap(new_img[i, ...]) for i in range(maximum)]
    cmap_img = (255*np.delete(color_transformed, 3, 3)).astype(np.uint8)

    # Figure out extension
    ext = '.{}'.format(parse_filename(filename)[2])
    # Write gif file
    mimwrite_(filename.replace(ext, '_{}.gif'.format(colormap)),
             cmap_img, format='gif', fps=int(fps * size))


def mimwrite_(filename, img, fps=18, **kwargs):
    """Helper to provide compatibility with older/newer versions of imageio
    """
    if tuple(map(int, imageio.__version__.split('.'))) > (2, 28):
        return mimwrite(filename, img, duration=int(1000/fps), **kwargs)
    else:
        return mimwrite(filename, img, fps=fps, **kwargs)
