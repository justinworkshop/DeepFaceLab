﻿import pickle
from pathlib import Path

import cv2

from DFLIMG import *
from facelib import LandmarksProcessor, FaceType
from core.interact import interact as io
from core import pathex
from core.cv2ex import *


def save_faceset_metadata_folder(input_path):
    input_path = Path(input_path)

    metadata_filepath = input_path / 'meta.dat'

    io.log_info (f"保存元数据到 {str(metadata_filepath)}\r\n")

    d = {}
    for filepath in io.progress_bar_generator( pathex.get_image_paths(input_path), "处理中..."):
        filepath = Path(filepath)
        dflimg = DFLIMG.load (filepath)
        if dflimg is None or not dflimg.has_data():
            io.log_info(f"{filepath} 不符合DFL规范")
            continue
            
        dfl_dict = dflimg.get_dict()
        d[filepath.name] = ( dflimg.get_shape(), dfl_dict )

    try:
        with open(metadata_filepath, "wb") as f:
            f.write ( pickle.dumps(d) )
    except:
        raise Exception( '保存出错 %s' % (filename) )

    io.log_info("现在可以编辑文件了")
    io.log_info("!!! 切记不要改文件名")
    io.log_info("你可以修改图片的大小，恢复程序会恢复到原始大小")
    io.log_info("处理完成之后，可以用恢复脚本恢复元数据")

def restore_faceset_metadata_folder(input_path):
    input_path = Path(input_path)

    metadata_filepath = input_path / 'meta.dat'
    io.log_info (f"从 {str(metadata_filepath)}.\r\n 恢复元数据")

    if not metadata_filepath.exists():
        io.log_err(f"没有发现 {str(metadata_filepath)}.")

    try:
        with open(metadata_filepath, "rb") as f:
            d = pickle.loads(f.read())
    except:
        raise FileNotFoundError(filename)

    for filepath in io.progress_bar_generator( pathex.get_image_paths(input_path, image_extensions=['.jpg'], return_Path_class=True), "处理中..."):
        saved_data = d.get(filepath.name, None)
        if saved_data is None:
            io.log_info(f"No saved metadata for {filepath}")
            continue
        
        shape, dfl_dict = saved_data

        img = cv2_imread (filepath)
        if img.shape != shape:
            img = cv2.resize (img, (shape[1], shape[0]), interpolation=cv2.INTER_LANCZOS4 )

            cv2_imwrite (str(filepath), img, [int(cv2.IMWRITE_JPEG_QUALITY), 100] )

        if filepath.suffix == '.jpg':
            dflimg = DFLJPG.load(filepath)
            dflimg.set_dict(dfl_dict)
            dflimg.save()
        else:
            continue

    metadata_filepath.unlink()

def add_landmarks_debug_images(input_path):
    io.log_info ("生成具有人脸轮廓标识的图片...")

    for filepath in io.progress_bar_generator( pathex.get_image_paths(input_path), "处理中..."):
        filepath = Path(filepath)

        img = cv2_imread(str(filepath))

        dflimg = DFLIMG.load (filepath)

        if dflimg is None or not dflimg.has_data():
            io.log_err (f"{filepath.name} 不符合DFL图片规范")
            continue
        
        if img is not None:
            face_landmarks = dflimg.get_landmarks()
            face_type = FaceType.fromString ( dflimg.get_face_type() )
            
            if face_type == FaceType.MARK_ONLY:
                rect = dflimg.get_source_rect()
                LandmarksProcessor.draw_rect_landmarks(img, rect, face_landmarks, FaceType.FULL )
            else:
                LandmarksProcessor.draw_landmarks(img, face_landmarks, transparent_mask=True )
            
            
            
            output_file = '{}{}'.format( str(Path(str(input_path)) / filepath.stem),  '_debug.jpg')
            cv2_imwrite(output_file, img, [int(cv2.IMWRITE_JPEG_QUALITY), 50] )

def recover_original_aligned_filename(input_path):
    io.log_info ("恢复原始文件名...")

    files = []
    for filepath in io.progress_bar_generator( pathex.get_image_paths(input_path), "处理中..."):
        filepath = Path(filepath)

        dflimg = DFLIMG.load (filepath)

        if dflimg is None or not dflimg.has_data():
            io.log_err (f"{filepath.name} 不符合DFL图片规范")
            continue

        files += [ [filepath, None, dflimg.get_source_filename(), False] ]

    files_len = len(files)
    for i in io.progress_bar_generator( range(files_len), "排序中..." ):
        fp, _, sf, converted = files[i]

        if converted:
            continue

        sf_stem = Path(sf).stem

        files[i][1] = fp.parent / ( sf_stem + '_0' + fp.suffix )
        files[i][3] = True
        c = 1

        for j in range(i+1, files_len):
            fp_j, _, sf_j, converted_j = files[j]
            if converted_j:
                continue

            if sf_j == sf:
                files[j][1] = fp_j.parent / ( sf_stem + ('_%d' % (c)) + fp_j.suffix )
                files[j][3] = True
                c += 1

    for file in io.progress_bar_generator( files, "重命名...", leave=False ):
        fs, _, _, _ = file
        dst = fs.parent / ( fs.stem + '_tmp' + fs.suffix )
        try:
            fs.rename (dst)
        except:
            io.log_err ('重命名失败 %s' % (fs.name) )

    for file in io.progress_bar_generator( files, "重命名..." ):
        fs, fd, _, _ = file
        fs = fs.parent / ( fs.stem + '_tmp' + fs.suffix )
        try:
            fs.rename (fd)
        except:
            io.log_err ('重命名失败 %s' % (fs.name) )

def export_faceset_mask(input_dir):
    for filename in io.progress_bar_generator(pathex.get_image_paths (input_dir), "Processing"):
        filepath = Path(filename)

        if '_mask' in filepath.stem:
            continue

        mask_filepath = filepath.parent / (filepath.stem+'_mask'+filepath.suffix)

        dflimg = DFLJPG.load(filepath)

        H,W,C = dflimg.shape

        seg_ie_polys = dflimg.get_seg_ie_polys()

        if dflimg.has_xseg_mask():
            mask = dflimg.get_xseg_mask()
            mask[mask < 0.5] = 0.0
            mask[mask >= 0.5] = 1.0
        elif seg_ie_polys.has_polys():
            mask = np.zeros ((H,W,1), dtype=np.float32)
            seg_ie_polys.overlay_mask(mask)
        else:
            raise Exception(f'no mask in file {filepath}')


        cv2_imwrite(mask_filepath, (mask*255).astype(np.uint8), [int(cv2.IMWRITE_JPEG_QUALITY), 100] )