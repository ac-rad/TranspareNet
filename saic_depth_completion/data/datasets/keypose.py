import os
import torch

import numpy as np
np.random.seed(0)
from PIL import Image
import OpenEXR
import Imath
import glob
from skimage.transform import resize
import cv2

ROOT = "/h/helen/datasets_slow/keypose"

def exr_loader_cv(EXR_PATH):
    image = cv2.imread(EXR_PATH, cv2.IMREAD_ANYCOLOR | cv2.IMREAD_ANYDEPTH).numpy()
    # check to make sure is two dimensional
    assert len(image.shape) == 2, f'Image is not two dimensional! {image.shape}'

def exr_loader(EXR_PATH, ndim=3):
    """Loads a .exr file as a numpy array
    Args:
        EXR_PATH: path to the exr file
        ndim: number of channels that should be in returned array. Valid values are 1 and 3.
                        if ndim=1, only the 'R' channel is taken from exr file
                        if ndim=3, the 'R', 'G' and 'B' channels are taken from exr file.
                            The exr file must have 3 channels in this case.
    Returns:
        numpy.ndarray (dtype=np.float32): If ndim=1, shape is (height x width)
                                          If ndim=3, shape is (3 x height x width)
    """

    exr_file = OpenEXR.InputFile(EXR_PATH)
    cm_dw = exr_file.header()['dataWindow']
    size = (cm_dw.max.x - cm_dw.min.x + 1, cm_dw.max.y - cm_dw.min.y + 1)

    pt = Imath.PixelType(Imath.PixelType.FLOAT)

    if ndim == 3:
        # read channels indivudally
        allchannels = []
        for c in ['R', 'G', 'B']:
            # transform data to numpy
            channel = np.frombuffer(exr_file.channel(c, pt), dtype=np.float32)
            channel.shape = (size[1], size[0])
            allchannels.append(channel)

        # create array and transpose dimensions to match tensor style
        exr_arr = np.array(allchannels).transpose((0, 1, 2))
        return exr_arr

    if ndim == 1:
        # print('exr path', EXR_PATH)
        # image = cv2.imread(EXR_PATH, cv2.IMREAD_ANYCOLOR | cv2.IMREAD_ANYDEPTH).numpy()
        # assert len(image.shape) == 2, f'Image is not two dimensional! {image.shape}'
        # transform data to numpy
        # print(exr_file.header())
        try:
            channel = np.frombuffer(exr_file.channel('R', pt), dtype=np.float32)
        except:
            channel = np.frombuffer(exr_file.channel('D', pt), dtype=np.float32)
        
        channel.shape = (size[1], size[0])  # Numpy arrays are (row, col)
        exr_arr = np.array(channel)
        return exr_arr
        # return image

def png_loader(path_to_png):
    image = np.array(Image.open(path_to_png).convert('L')) / 255. # .transpose([2, 0, 1])
    mask = np.zeros_like(image)
    mask[np.where(image <= 0.01)] = 1
    return mask


class KeyPose:
    def __init__(
            self, root=ROOT, split="train", transforms=None, processed=True
    ):
        # Split options: bottle_0, bottle_1, bottle_2, cup_0, cup_1 
        # Split can be train or test-val
        self.transforms = transforms
        self.split = split
        # if split in ['val','test']:
        #     split = 'test-val'
        self.data_root = os.path.join(root,split,'data',split) # os.path.join(root, "data")
        # self.split_file = os.path.join(root, "splits", split + ".txt")
        # self.data_list = self._get_data_list(self.split_file)
        self.color_name, self.depth_name, self.render_name,self.mask_name = [], [], [], []
        self.normal_name = []
        self.processed = processed
        self._load_data(processed=processed)
        

    def _load_data(self,processed=True):

        # List of extensions
        EXT_COLOR_IMG = ['_L.png']  #'-rgb.jpg' - includes normals-rgb.jpg
        EXT_DEPTH_IMG = ['_Dt.exr']
        EXT_DEPTH_GT = ['_Do.exr']
        EXT_MASK = ['_mask.png']

        # Check if split is test or validation
        split_type = self.split

        for placement in os.listdir(self.data_root):
            # print(os.path.join(self.data_root,placement))
            # for files in os.listdir(self.data_root,placement):
            for ext in EXT_COLOR_IMG:
                color_f = sorted(glob.glob(os.path.join(self.data_root,placement,'*' +ext)),key = lambda x: int(x.split('/')[-1].split('_')[0]))
                self.color_name += color_f
            for ext in EXT_DEPTH_IMG:
                depth_f = sorted(glob.glob(os.path.join(self.data_root,placement,'*' +ext)),key = lambda x: int(x.split('/')[-1].split('_')[0]))
                self.depth_name += depth_f
            for ext in EXT_DEPTH_GT:
                render_depth_f = sorted(glob.glob(os.path.join(self.data_root,placement,'*' +ext)),key = lambda x: int(x.split('/')[-1].split('_')[0]))
                self.render_name += render_depth_f
            for ext in EXT_MASK:
                mask_f = sorted(glob.glob(os.path.join(self.data_root,placement,'*' +ext)),key = lambda x: int(x.split('/')[-1].split('_')[0]))
                self.mask_name += mask_f

        # else:
        #     raise ValueError('dataloading error, please provide a reasonable split')


    def __len__(self):
        return len(self.depth_name)

    def __getitem__(self, index):
        color           = np.array(Image.open(self.color_name[index])).transpose([2, 0, 1]) / 255. # exr_loader(self.color_name[index], ndim=3) / 255.  #np.array(Image.open(self.color_name[index])).transpose([2, 0, 1]) / 255.
        render_depth    = exr_loader(self.render_name[index], ndim=1) # np.array(Image.open(self.render_name[index])) / 4000.
        depth           = exr_loader(self.depth_name[index], ndim=1) #np.array(Image.open(self.depth_name[index])) / 4000.

        # Load the mask
        mask = png_loader(self.mask_name[index])

        if self.depth_name[index].endswith('depth-rectified.exr'):
            # Remove the portion of the depth image with transparent object
            # If image is synthetic
            depth[np.where(mask==0)] = 0
        
        # Resize arrays:
        
        color =resize(color, (3,480,640))
        assert len(render_depth.shape) == 2 , 'There is channel dimension'
        render_depth = resize(render_depth,(480,640))
        depth =resize(depth,(480,640))
        mask = resize(mask,(480,640))

        render_depth[np.isnan(render_depth)] = 0.0
        render_depth[np.isinf(render_depth)] = 0.0

        # print('max_pixel_depth', np.amax(depth))
        # print('max_pixel_gt', np.amax(render_depth))
        
        # Clip depths
        depth[depth>1.5] = 1.5
        render_depth[render_depth>1.5] = 1.5

        return  {
            'color':        torch.tensor(color, dtype=torch.float32),
            'raw_depth':    torch.tensor(depth, dtype=torch.float32).unsqueeze(0),
            'mask':         torch.tensor(mask, dtype=torch.float32).unsqueeze(0),
            #'normals':      torch.tensor(normals, dtype=torch.float32).unsqueeze(0),
            'gt_depth':     torch.tensor(render_depth, dtype=torch.float32).unsqueeze(0),
        }