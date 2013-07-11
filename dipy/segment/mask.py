import numpy as np
import copy
from scipy.ndimage import binary_opening, label
from scipy.ndimage.filters import median_filter

def medotsu(input_volume, median_radius=4, numpass=4, autocrop=False):
    """
    Simple brain extraction tool method for b0 images from DWI data. It uses a median filter 
    smoothing of the input_volume and an automatic histogram Otsu thresholding technique, hence
    the name medostsu. 

    It mimics the MRtrix bet from the documentation.
    (mrconvert dwi.nii -coord 3 0 - | threshold - - | median3D - - | median3D - mask.nii)
    MRtrix uses default mean_radius=3 and numpass=2
    
    However, from tests on multiple 1.5T and 3T data from GE, Philips, Siemens, the most
    robust choice is median_radis=4, numpass=4
    Parameters
    ----------
    input_volume : 3D ndarray
        3D ndarray of the b=0 volume 
    median_radius : int
        Radius of the applied median filter (default 4)
    numpass: int
        Number of pass of the median filter (default 4)
    autocrop: bool, optional
        if True, the masked input_volume will also be cropped using the bounding box
        defined by the masked data. Should be on if DWI is upsampled to 1x1x1 resolution.
        (default False)

    Returns
    -------
    input_volume : 3D ndarray
        Masked input_volume
    mask : 3D ndarray
        The binary brain mask
    """

    # The original data will be needed for final crop / mask
    vol = input_volume.copy()

    # Make a mask using a multiple pass median filter and histogram thresholding.
    mask = multi_median(vol, median_radius, numpass)
    thresh = otsu(mask)
    binary_threshold(mask, thresh)
    
    # Auto crop the volumes using the mask as input_volume for bounding box computing.
    if autocrop:
        mins, maxs = bounding_box(mask)
        mask = crop(mask, mins, maxs)
        input_volume = crop(input_volume, mins, maxs)

    # Apply the cropped mask to the cropped original volume.
    applymask(input_volume, mask)

    return input_volume, mask


def multi_median(input, median_radius, numpass):
    """
    Applies multiple times scikit's median filter on input data.

    Parameters
    ----------
    input : ndarray
        The input volume to apply filter on.
    median_radius : int
        Radius of the applied median filter
    numpass: int
        Number of pass of the median filter
    Returns
    -------
        input : ndarray
            Filtered input volume.
    """
    outvol = np.zeros_like(input, dtype=input.dtype)
    
    # Array representing the size of the median window in each dimension.
    medarr = np.ones_like(input.shape) * ((median_radius * 2) +1)
    
    # Multi pass
    for i in range(0, numpass):
        median_filter(input, medarr, output=input)

    return input

def otsu(image, nbins=256):
    """Return threshold value based on Otsu's method.

    Copied from scikit-image to remove dependency.

    Parameters
    ----------
    image : array
        Input image.
    nbins : int
        Number of bins used to calculate histogram. This value is ignored for
        integer arrays.

    Returns
    -------
    threshold : float
        Threshold value.
    """
    hist, bin_centers = np.histogram(image, nbins)
    hist = hist.astype(float)

    # class probabilities for all possible thresholds
    weight1 = np.cumsum(hist)
    weight2 = np.cumsum(hist[::-1])[::-1]

    # class means for all possible thresholds
    mean1 = np.cumsum(hist * bin_centers[1:]) / weight1
    mean2 = (np.cumsum((hist * bin_centers[1:])[::-1]) / weight2[::-1])[::-1]

    # Clip ends to align class 1 and class 2 variables:
    # The last value of `weight1`/`mean1` should pair with zero values in
    # `weight2`/`mean2`, which do not exist.
    variance12 = weight1[:-1] * weight2[1:] * (mean1[:-1] - mean2[1:])**2

    idx = np.argmax(variance12)
    threshold = bin_centers[:-1][idx]
    return threshold


def applymask(vol, mask):
    """
    Recursively applies N dimensionnal mask to a M dimensionnal volume
    for N <= M.

    Parameters
    ----------
        vol : ndarray
            Volume to apply mask on.
        mask : ndarray
            Binary mask.
    """
    if len(mask.shape) > len(vol.shape):
        raise Exception('applymask: The mask\'s dimmensionnality is bigger than the input\'s')

    elif len(mask.shape) > len(vol.shape):
        lastdimelen = vol.shape[len(vol.shape)-1]
        for i in range(0,lastdimlen):
            applymask(vol[..., i], mask)
    else:
        outliers = np.where(mask == 0)
        outliers = np.array(outliers)
        outliers = tuple(outliers)
        vol[outliers] = 0


def binary_threshold(vol, thresh):
    """
    Simple binary thresholding.

    Parameters
    ----------
        vol : ndarray
            Volume to apply threshold on.
        thresh : float
            Thresholding value.
    """
    maxval = maxvalue(vol.dtype)
    for x in np.nditer(vol, flags=['external_loop','buffered'],
                       op_flags=['readwrite'], order='F'):

        x[np.where(x > thresh)] = maxval
        x[np.where(x <= thresh)] = 0

def maxvalue(datatype):
    """
    Returns the maxvalue of the input datatype.

    Parameters
    ----------
        datatype : dtype
            Datatype to get max value.

    Returns
    -------
        maxvalue : numeric
            Maximum possible value of the input datatype
    """
    if datatype.kind in 'iu':
        return np.iinfo(datatype.type).max
    else:
        return np.finfo(datatype.type).max

def bounding_box(vol):
    """
    Compute the bounding box of nonzero intensity voxels in the volume.

    Parameters
    ----------
        vol : ndarray
            Volume to compute bounding box on.

    Returns
    -------
        npmins : array
            Array containg minimum index of each dimension
        npmaxs : array
            Array containg maximum index of each dimension
    """
    pts = np.array(np.where(vol != 0)).T

    if len(pts) == 0:
        print 'WARNING: Not data found in volume to bound. Returning empty bounding box.'
        return [0,0,0], [0,0,0]

    maxs = copy.copy(pts[0])
    mins = copy.copy(pts[0])
    numdims = len(pts[0])

    for pt in pts:
        for curdim in range(0, numdims):
            if pt[curdim] > maxs[curdim]:
                maxs[curdim] = copy.copy(pt[curdim])

            if pt[curdim] < mins[curdim]:
                mins[curdim] = copy.copy(pt[curdim])

    npmaxs = np.array(maxs)
    npmins = np.array(mins)
    return npmins, npmaxs

def crop(vol, mins, maxs):
    """
    Crops the input volume.

    Parameters
    ----------
        vol : 3D ndarray
            Volume to crop.
        mins : array
            Array containg minimum index of each dimension.
        maxs : array
            Array containg maximum index of each dimension.

    Returns
    -------
        vol : 3D ndarray
            The cropped volume.
    """
    return vol[mins[0]:maxs[0]+1, mins[1]:maxs[1]+1, mins[2]:maxs[2]+1]
