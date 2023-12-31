import pickle
import shutil
import struct
from pathlib import Path

import samplelib.SampleLoader
from core.interact import interact as io
from samplelib import Sample
from core import pathex

packed_faceset_filename = 'faceset.pak'

class PackedFaceset():
    VERSION = 1

    @staticmethod
    def pack(samples_path):
        samples_dat_path = samples_path / packed_faceset_filename

        if samples_dat_path.exists():
            io.log_info(f"{samples_dat_path} : 文件已经存在 !")
            io.input("按任意键继续并覆盖文件")

        as_person_faceset = False
        dir_names = pathex.get_all_dir_names(samples_path)
        if len(dir_names) != 0:
            as_person_faceset = io.input_bool(f"{len(dir_names)} 找到子目录，作为人脸集处理?", True)

        if as_person_faceset:
            image_paths = []

            for dir_name in dir_names:
                image_paths += pathex.get_image_paths(samples_path / dir_name)
        else:
            image_paths = pathex.get_image_paths(samples_path)

        samples = samplelib.SampleLoader.load_face_samples(image_paths)
        samples_len = len(samples)

        samples_configs = []
        for sample in io.progress_bar_generator (samples, "处理中..."):
            sample_filepath = Path(sample.filename)
            sample.filename = sample_filepath.name

            if as_person_faceset:
                sample.person_name = sample_filepath.parent.name
            samples_configs.append ( sample.get_config() )
        samples_bytes = pickle.dumps(samples_configs, 4)

        of = open(samples_dat_path, "wb")
        of.write ( struct.pack ("Q", PackedFaceset.VERSION ) )
        of.write ( struct.pack ("Q", len(samples_bytes) ) )
        of.write ( samples_bytes )

        del samples_bytes   #just free mem
        del samples_configs

        sample_data_table_offset = of.tell()
        of.write ( bytes( 8*(samples_len+1) ) ) #sample data offset table

        data_start_offset = of.tell()
        offsets = []

        for sample in io.progress_bar_generator(samples, "打包中..."):
            try:
                if sample.person_name is not None:
                    sample_path = samples_path / sample.person_name / sample.filename
                else:
                    sample_path = samples_path / sample.filename


                with open(sample_path, "rb") as f:
                   b = f.read()

                offsets.append ( of.tell() - data_start_offset )
                of.write(b)
            except:
                raise Exception(f"出现了错误，路径： {sample_path}")

        offsets.append ( of.tell() )

        of.seek(sample_data_table_offset, 0)
        for offset in offsets:
            of.write ( struct.pack("Q", offset) )
        of.seek(0,2)
        of.close()
        
        if io.input_bool(f"删除原始文件?", True):
            for filename in io.progress_bar_generator(image_paths, "删除文件"):
                Path(filename).unlink()

            if as_person_faceset:
                for dir_name in io.progress_bar_generator(dir_names, "删除目录"):
                    dir_path = samples_path / dir_name
                    try:
                        shutil.rmtree(dir_path)
                    except:
                        io.log_info (f"无法删除: {dir_path} ")

    @staticmethod
    def unpack(samples_path):
        samples_dat_path = samples_path / packed_faceset_filename
        if not samples_dat_path.exists():
            io.log_info(f"{samples_dat_path} : 文件不存在.")
            return

        samples = PackedFaceset.load(samples_path)

        for sample in io.progress_bar_generator(samples, "解包中..."):
            person_name = sample.person_name
            if person_name is not None:
                person_path = samples_path / person_name
                person_path.mkdir(parents=True, exist_ok=True)

                target_filepath = person_path / sample.filename
            else:
                target_filepath = samples_path / sample.filename

            with open(target_filepath, "wb") as f:
                f.write( sample.read_raw_file() )

        samples_dat_path.unlink()

    @staticmethod
    def path_contains(samples_path):
        samples_dat_path = samples_path / packed_faceset_filename
        return samples_dat_path.exists()
    
    @staticmethod
    def load(samples_path):
        samples_dat_path = samples_path / packed_faceset_filename
        if not samples_dat_path.exists():
            return None

        f = open(samples_dat_path, "rb")
        version, = struct.unpack("Q", f.read(8) )
        if version != PackedFaceset.VERSION:
            raise NotImplementedError

        sizeof_samples_bytes, = struct.unpack("Q", f.read(8) )

        samples_configs = pickle.loads ( f.read(sizeof_samples_bytes) )
        samples = []
        for sample_config in samples_configs:
            sample_config = pickle.loads(pickle.dumps (sample_config))
            samples.append ( Sample (**sample_config) )

        offsets = [ struct.unpack("Q", f.read(8) )[0] for _ in range(len(samples)+1) ]
        data_start_offset = f.tell()
        f.close()

        for i, sample in enumerate(samples):
            start_offset, end_offset = offsets[i], offsets[i+1]
            sample.set_filename_offset_size( str(samples_dat_path), data_start_offset+start_offset, end_offset-start_offset )

        return samples
