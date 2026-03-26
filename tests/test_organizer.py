from app.organizer import JAVOrganizer


class TestJAVOrganizer:
    def test_get_filename_parts_normalizes_suffix_variants(self):
        organizer = JAVOrganizer('/tmp/dist')

        test_cases = [
            ('FPRE-123C.mp4', ('FPRE-123', '.mp4', '-C')),
            ('MVSD-662-C.mp4', ('MVSD-662', '.mp4', '-C')),
            ('MVSD-662-UC.mkv', ('MVSD-662', '.mkv', '-UC')),
            ('FPRE-123_字幕版.mp4', ('FPRE-123', '.mp4', '-C')),
            ('SSIS-123字幕版.mp4', ('SSIS-123', '.mp4', '-C')),
            ('SSIS-123.mp4', ('SSIS-123', '.mp4', None)),
            ('MEYD-695 出轨xxx@北野未奈.mp4', ('MEYD-695', '.mp4', None)),
            ('HMN-439-C.H265.mp4', ('HMN-439', '.mp4', '-C')),
            ('CEMD-721ch.mp4', ('CEMD-721', '.mp4', '-C')),
            ('HMN-112-C マジxxx痴 北野未奈.mp4', ('HMN-112', '.mp4', '-C')),
            ('ABC-123 [Uncensored].mp4', ('ABC-123', '.mp4', '-UC')),
        ]

        for filename, expected in test_cases:
            assert organizer.get_filename_parts(filename) == expected

    def test_generate_filename_normalizes_compact_suffix(self):
        organizer = JAVOrganizer('/tmp/dist')

        assert organizer.generate_filename('FPRE-123', 'FPRE-123C.mp4') == 'FPRE-123-C.mp4'
        assert organizer.generate_filename('MVSD-662', 'MVSD-662-C.mp4') == 'MVSD-662-C.mp4'
        assert organizer.generate_filename('MVSD-662', 'MVSD-662-UC.mkv') == 'MVSD-662-UC.mkv'
        assert organizer.generate_filename('FPRE-123', 'FPRE-123_字幕版.mp4') == 'FPRE-123-C.mp4'
        assert organizer.generate_filename('SSIS-123', 'SSIS-123.mp4') == 'SSIS-123.mp4'
        assert organizer.generate_filename('MEYD-695', 'MEYD-695 出轨xxx@北野未奈.mp4') == 'MEYD-695.mp4'
        assert organizer.generate_filename('HMN-439', 'HMN-439-C.H265.mp4') == 'HMN-439-C.mp4'
        assert organizer.generate_filename('CEMD-721', 'CEMD-721ch.mp4') == 'CEMD-721-C.mp4'
        assert organizer.generate_filename('HMN-112', 'HMN-112-C マジxxx痴 北野未奈.mp4') == 'HMN-112-C.mp4'
        assert organizer.generate_filename('ABC-123', 'ABC-123 [Uncensored].mp4') == 'ABC-123-UC.mp4'

    def test_get_target_path_uses_pure_code_directory(self):
        organizer = JAVOrganizer('/vol2/1000/porn/OrderedJAV')

        assert (
            organizer.get_target_path('FPRE-123', 'FPRE-123C.mp4')
            == '/vol2/1000/porn/OrderedJAV/FPRE-123/FPRE-123-C.mp4'
        )
        assert (
            organizer.get_target_path('MVSD-662', 'MVSD-662-C.mp4')
            == '/vol2/1000/porn/OrderedJAV/MVSD-662/MVSD-662-C.mp4'
        )
        assert (
            organizer.get_target_path('FPRE-123', 'FPRE-123_字幕版.mp4')
            == '/vol2/1000/porn/OrderedJAV/FPRE-123/FPRE-123-C.mp4'
        )
        assert (
            organizer.get_target_path('MEYD-695', 'MEYD-695 出轨xxx@北野未奈.mp4')
            == '/vol2/1000/porn/OrderedJAV/MEYD-695/MEYD-695.mp4'
        )
        assert (
            organizer.get_target_path('HMN-439', 'HMN-439-C.H265.mp4')
            == '/vol2/1000/porn/OrderedJAV/HMN-439/HMN-439-C.mp4'
        )
        assert (
            organizer.get_target_path('CEMD-721', 'CEMD-721ch.mp4')
            == '/vol2/1000/porn/OrderedJAV/CEMD-721/CEMD-721-C.mp4'
        )
        assert (
            organizer.get_target_path('HMN-112', 'HMN-112-C マジxxx痴 北野未奈.mp4')
            == '/vol2/1000/porn/OrderedJAV/HMN-112/HMN-112-C.mp4'
        )

    def test_move_file_reports_existing_target(self, tmp_path):
        organizer = JAVOrganizer(str(tmp_path / 'dist'))
        source = tmp_path / 'source' / 'FPRE-123_字幕版.mp4'
        target = tmp_path / 'dist' / 'FPRE-123' / 'FPRE-123-C.mp4'

        source.parent.mkdir(parents=True, exist_ok=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        source.write_text('source fixture')
        target.write_text('existing target')

        success, reason = organizer.move_file(str(source), str(target))

        assert success is False
        assert reason == '目标文件已存在'
