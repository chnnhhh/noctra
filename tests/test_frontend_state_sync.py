import json
import subprocess
import textwrap
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_frontend_script(script: str) -> dict:
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout.strip())


def test_refresh_after_batch_completion_invalidates_stale_scrape_cache():
    script = textwrap.dedent(
        """
        import fs from 'node:fs';
        import vm from 'node:vm';

        const context = vm.createContext({
          console,
          setTimeout,
          clearTimeout,
          setInterval,
          clearInterval,
          Intl,
          URLSearchParams,
          Date,
        });
        context.window = context;
        context.globalThis = context;

        for (const path of ['static/js/state.js', 'static/js/features.js']) {
          const source = fs.readFileSync(path, 'utf8');
          vm.runInContext(source, context, { filename: path });
        }

        function mergeSection(target, section) {
          Object.defineProperties(target, Object.getOwnPropertyDescriptors(section));
          return target;
        }

        const app = {};
        mergeSection(app, context.NoctraState.createState());
        mergeSection(app, context.NoctraFeatures.createFeatures());

        let loadScrapeCalls = 0;
        app.loadScrapeFiles = async function () {
          loadScrapeCalls += 1;
          this.scrapeLoaded = true;
        };

        context.fetch = async (url) => {
          if (url !== '/api/scan') {
            throw new Error(`unexpected url: ${url}`);
          }

          return {
            ok: true,
            async json() {
              return {
                total_files: 1,
                identified: 1,
                unidentified: 0,
                pending: 0,
                processed: 1,
                files: [
                  {
                    id: 1,
                    original_path: '/source/ABC-001.mp4',
                    identified_code: 'ABC-001',
                    target_path: '/dist/ABC-001/ABC-001.mp4',
                    status: 'processed',
                    file_size: 1024,
                    file_mtime: 1700000000,
                    created_at: '2026-03-28T00:00:00',
                    updated_at: '2026-03-28T00:00:00',
                  },
                ],
              };
            },
          };
        };

        app.scrapeLoaded = true;
        app.scrapeFilesCache = [
          {
            id: 99,
            identified_code: 'STALE-999',
            scrape_status: 'pending',
          },
        ];

        await app.refreshAfterBatchCompletion();
        const scrapeLoadedAfterRefresh = app.scrapeLoaded;

        await app.switchView('scrape');

        console.log(JSON.stringify({
          scrapeLoadedAfterRefresh,
          loadScrapeCalls,
          finalView: app.view,
        }));
        """
    )

    result = run_frontend_script(script)

    assert result["scrapeLoadedAfterRefresh"] is False
    assert result["loadScrapeCalls"] == 1
    assert result["finalView"] == "scrape"


def test_scrape_batch_panel_surfaces_concise_progress_copy():
    script = textwrap.dedent(
        """
        import fs from 'node:fs';
        import vm from 'node:vm';

        const context = vm.createContext({
          console,
          setTimeout,
          clearTimeout,
          setInterval,
          clearInterval,
          Intl,
          URLSearchParams,
          Date,
        });
        context.window = context;
        context.globalThis = context;

        for (const path of ['static/js/state.js', 'static/js/render.js']) {
          const source = fs.readFileSync(path, 'utf8');
          vm.runInContext(source, context, { filename: path });
        }

        function mergeSection(target, section) {
          Object.defineProperties(target, Object.getOwnPropertyDescriptors(section));
          return target;
        }

        const app = {};
        mergeSection(app, context.NoctraState.createState());
        mergeSection(app, context.NoctraRender.createRender());

        app.scrapeBatchJob = {
          status: 'running',
          total: 3,
          processed: 1,
          succeeded: 1,
          failed: 0,
          current_file_code: 'SSIS-123',
          current_stage: 'writing_nfo',
          current_source: 'javdb',
          recent_logs: [
            {
              at: '2026-03-28T10:00:00',
              level: 'info',
              stage: 'writing_nfo',
              source: 'javdb',
              message: '元数据解析成功，正在生成 NFO 文件',
            },
          ],
        };

        console.log(JSON.stringify({
          taskLabel: app.scrapeBatchTaskLabel,
          currentFileText: app.scrapeBatchCurrentFileText,
          currentStageText: app.scrapeBatchCurrentStageText,
          latestProgressText: app.scrapeBatchLatestProgressText,
        }));
        """
    )

    result = run_frontend_script(script)

    assert result["taskLabel"] == "刮削任务"
    assert result["currentFileText"] == "SSIS-123"
    assert result["currentStageText"] == "元数据解析成功，正在生成 NFO 文件"
    assert result["latestProgressText"] == "元数据解析成功，正在生成 NFO 文件"


def test_scrape_batch_panel_markup_lives_inside_scrape_tab():
    html = (PROJECT_ROOT / "static/index.html").read_text(encoding="utf-8")

    scrape_tab_start = html.index("<!-- Scrape Tab -->")
    scrape_panel = html.index('x-show="view === \'scrape\' && scrapeBatchPanelVisible"')

    assert scrape_panel > scrape_tab_start


def test_scrape_status_static_branch_uses_single_root_node():
    html = (PROJECT_ROOT / "static/index.html").read_text(encoding="utf-8")

    branch_start = html.index('<template x-if="!hasScrapeStatusAction(file)">')
    branch = html[branch_start:branch_start + 700]

    assert '<div class="status-static">' in branch
    assert branch.index('<div class="status-static">') < branch.index('<button class="badge clickable"')
    assert branch.index('<div class="status-static">') < branch.index('<span class="badge"')


def test_scrape_success_action_branch_keeps_direct_clickable_status_trigger():
    html = (PROJECT_ROOT / "static/index.html").read_text(encoding="utf-8")

    branch_start = html.index('<template x-if="hasScrapeStatusAction(file)">')
    branch = html[branch_start:branch_start + 3200]

    assert "file.scrape_status === 'success'" in branch
    assert '@click="showScrapeDetail(file)"' in branch
    assert branch.index('class="status-trigger clickable"') < branch.index('<div class="status-actions">')


def test_status_action_mobile_layout_overrides_generic_button_width():
    css = (PROJECT_ROOT / "static/css/index.css").read_text(encoding="utf-8")

    assert ".status-action .status-trigger" in css
    assert ".status-action .icon-action" in css


def test_load_scrape_files_clears_stale_batch_overlay_when_no_active_job():
    script = textwrap.dedent(
        """
        import fs from 'node:fs';
        import vm from 'node:vm';

        const context = vm.createContext({
          console,
          setTimeout,
          clearTimeout,
          setInterval,
          clearInterval,
          Intl,
          URLSearchParams,
          Date,
        });
        context.window = context;
        context.globalThis = context;

        for (const path of ['static/js/state.js', 'static/js/features.js']) {
          const source = fs.readFileSync(path, 'utf8');
          vm.runInContext(source, context, { filename: path });
        }

        context.ScrapeAPI = {
          async getList() {
            return {
              total: 1,
              items: [
                {
                  file_id: 13,
                  code: 'EBOD-829',
                  target_path: '/dist/EBOD-829/EBOD-829.mp4',
                  original_path: '/source/EBOD-829.mp4',
                  status: 'processed',
                  scrape_status: 'success',
                  last_scrape_at: '2026-03-28T02:07:03',
                },
              ],
              active_job: null,
            };
          },
        };

        function mergeSection(target, section) {
          Object.defineProperties(target, Object.getOwnPropertyDescriptors(section));
          return target;
        }

        const app = {};
        mergeSection(app, context.NoctraState.createState());
        mergeSection(app, context.NoctraFeatures.createFeatures());

        app.scrapeBatchJob = {
          id: 'job-old',
          status: 'completed',
          items: [
            {
              id: 13,
              status: 'processing',
            },
          ],
        };
        app.scrapeBatchItemsIndex = {
          13: {
            id: 13,
            status: 'processing',
          },
        };
        app.scrapeBatchExpanded = true;
        app.scrapeBatchCancelling = true;

        await app.loadScrapeFiles();

        console.log(JSON.stringify({
          scrapeBatchJob: app.scrapeBatchJob,
          scrapeBatchItemsIndex: app.scrapeBatchItemsIndex,
          scrapeBatchExpanded: app.scrapeBatchExpanded,
          scrapeBatchCancelling: app.scrapeBatchCancelling,
          scrapeStatus: app.scrapeFilesCache[0]?.scrape_status || null,
        }));
        """
    )

    result = run_frontend_script(script)

    assert result["scrapeBatchJob"] is None
    assert result["scrapeBatchItemsIndex"] == {}
    assert result["scrapeBatchExpanded"] is False
    assert result["scrapeBatchCancelling"] is False
    assert result["scrapeStatus"] == "success"


def test_scrape_success_rows_offer_rescrape_action():
    script = textwrap.dedent(
        """
        import fs from 'node:fs';
        import vm from 'node:vm';

        const context = vm.createContext({
          console,
          setTimeout,
          clearTimeout,
          setInterval,
          clearInterval,
          Intl,
          URLSearchParams,
          Date,
        });
        context.window = context;
        context.globalThis = context;

        for (const path of ['static/js/state.js', 'static/js/render.js']) {
          const source = fs.readFileSync(path, 'utf8');
          vm.runInContext(source, context, { filename: path });
        }

        function mergeSection(target, section) {
          Object.defineProperties(target, Object.getOwnPropertyDescriptors(section));
          return target;
        }

        const app = {};
        mergeSection(app, context.NoctraState.createState());
        mergeSection(app, context.NoctraRender.createRender());

        app.view = 'scrape';
        const file = {
          id: 13,
          scrape_status: 'success',
        };

        console.log(JSON.stringify({
          canSelect: app.canSelectScrapeFile(file),
          actions: app.getScrapeStatusActions(file),
        }));
        """
    )

    result = run_frontend_script(script)

    assert result["canSelect"] is False
    assert result["actions"] == [
        {"key": "scrape", "label": "重新刮削", "icon": "scrape"}
    ]


def test_show_scrape_detail_modal_loads_preview_payload():
    script = textwrap.dedent(
        """
        import fs from 'node:fs';
        import vm from 'node:vm';

        const context = vm.createContext({
          console,
          setTimeout,
          clearTimeout,
          setInterval,
          clearInterval,
          Intl,
          URLSearchParams,
          Date,
        });
        context.window = context;
        context.globalThis = context;

        for (const path of ['static/js/state.js', 'static/js/features.js']) {
          const source = fs.readFileSync(path, 'utf8');
          vm.runInContext(source, context, { filename: path });
        }

        context.ScrapeAPI = {
          async getDetail(fileId) {
            return {
              file_id: fileId,
              code: 'EBOD-829',
              poster_url: '/api/scrape/13/artifacts/EBOD-829-poster.jpg',
              files: ['EBOD-829.mp4', 'EBOD-829.nfo'],
              metadata: {
                code: 'EBOD-829',
                plot: '测试剧情简介',
                actors: ['演员A'],
                release_date: '2021-06-13',
                runtime: '140',
                tags: ['巨乳'],
              },
            };
          },
        };

        function mergeSection(target, section) {
          Object.defineProperties(target, Object.getOwnPropertyDescriptors(section));
          return target;
        }

        const app = {};
        mergeSection(app, context.NoctraState.createState());
        mergeSection(app, context.NoctraFeatures.createFeatures());

        await app.showScrapeDetail({
          id: 13,
          identified_code: 'EBOD-829',
          scrape_status: 'success',
        });

        console.log(JSON.stringify({
          showScrapeDetailModal: app.showScrapeDetailModal,
          scrapeDetailCode: app.scrapeDetailFile?.metadata?.code || null,
          scrapeDetailPoster: app.scrapeDetailFile?.poster_url || null,
          fileCount: app.scrapeDetailFile?.files?.length || 0,
        }));
        """
    )

    result = run_frontend_script(script)

    assert result["showScrapeDetailModal"] is True
    assert result["scrapeDetailCode"] == "EBOD-829"
    assert result["scrapeDetailPoster"] == "/api/scrape/13/artifacts/EBOD-829-poster.jpg"
    assert result["fileCount"] == 2


def test_scrape_detail_groups_preview_images_into_summary():
    script = textwrap.dedent(
        """
        import fs from 'node:fs';
        import vm from 'node:vm';

        const context = vm.createContext({
          console,
          setTimeout,
          clearTimeout,
          setInterval,
          clearInterval,
          Intl,
          URLSearchParams,
          Date,
        });
        context.window = context;
        context.globalThis = context;

        for (const path of ['static/js/render.js']) {
          const source = fs.readFileSync(path, 'utf8');
          vm.runInContext(source, context, { filename: path });
        }

        const render = context.NoctraRender.createRender();
        const grouped = render.getScrapeDetailArtifacts({
          file_id: 13,
          files: [
            'EBOD-829.mp4',
            'EBOD-829.nfo',
            'EBOD-829-poster.jpg',
            'EBOD-829-fanart.jpg',
            'EBOD-829-preview-01.jpg',
            'EBOD-829-preview-02.jpg',
            'EBOD-829-preview-03.jpg',
          ],
        });

        console.log(JSON.stringify(grouped));
        """
    )

    result = run_frontend_script(script)

    assert result["primaryFiles"] == [
        "EBOD-829.mp4",
        "EBOD-829.nfo",
        "EBOD-829-poster.jpg",
        "EBOD-829-fanart.jpg",
    ]
    assert result["previewCount"] == 3
    assert result["previewFiles"] == [
        {
            "name": "EBOD-829-preview-01.jpg",
            "url": "/api/scrape/13/artifacts/EBOD-829-preview-01.jpg",
        },
        {
            "name": "EBOD-829-preview-02.jpg",
            "url": "/api/scrape/13/artifacts/EBOD-829-preview-02.jpg",
        },
        {
            "name": "EBOD-829-preview-03.jpg",
            "url": "/api/scrape/13/artifacts/EBOD-829-preview-03.jpg",
        },
    ]


def test_open_scrape_preview_gallery_initializes_image_browser():
    script = textwrap.dedent(
        """
        import fs from 'node:fs';
        import vm from 'node:vm';

        const context = vm.createContext({
          console,
          setTimeout,
          clearTimeout,
          setInterval,
          clearInterval,
          Intl,
          URLSearchParams,
          Date,
        });
        context.window = context;
        context.globalThis = context;

        for (const path of ['static/js/state.js', 'static/js/render.js', 'static/js/features.js']) {
          const source = fs.readFileSync(path, 'utf8');
          vm.runInContext(source, context, { filename: path });
        }

        function mergeSection(target, section) {
          Object.defineProperties(target, Object.getOwnPropertyDescriptors(section));
          return target;
        }

        const app = {};
        mergeSection(app, context.NoctraState.createState());
        mergeSection(app, context.NoctraRender.createRender());
        mergeSection(app, context.NoctraFeatures.createFeatures());

        app.openScrapePreviewGallery({
          file_id: 13,
          files: [
            'EBOD-829.mp4',
            'EBOD-829-preview-01.jpg',
            'EBOD-829-preview-02.jpg',
            'EBOD-829-preview-03.jpg',
          ],
        }, 1);

        console.log(JSON.stringify({
          visible: app.showScrapePreviewGalleryModal,
          count: app.scrapePreviewGalleryImages.length,
          index: app.scrapePreviewGalleryIndex,
          currentName: app.currentScrapePreviewImage?.name || null,
        }));
        """
    )

    result = run_frontend_script(script)

    assert result["visible"] is True
    assert result["count"] == 3
    assert result["index"] == 1
    assert result["currentName"] == "EBOD-829-preview-02.jpg"


def test_show_next_scrape_preview_scrolls_active_thumbnail_into_view():
    script = textwrap.dedent(
        """
        import fs from 'node:fs';
        import vm from 'node:vm';

        const context = vm.createContext({
          console,
          setTimeout,
          clearTimeout,
          setInterval,
          clearInterval,
          Intl,
          URLSearchParams,
          Date,
        });
        context.window = context;
        context.globalThis = context;

        for (const path of ['static/js/state.js', 'static/js/render.js', 'static/js/features.js']) {
          const source = fs.readFileSync(path, 'utf8');
          vm.runInContext(source, context, { filename: path });
        }

        function mergeSection(target, section) {
          Object.defineProperties(target, Object.getOwnPropertyDescriptors(section));
          return target;
        }

        const calls = [];
        const app = {};
        mergeSection(app, context.NoctraState.createState());
        mergeSection(app, context.NoctraRender.createRender());
        mergeSection(app, context.NoctraFeatures.createFeatures());

        app.$nextTick = (callback) => callback();
        app.$refs = {
          scrapePreviewStrip: {
            querySelector(selector) {
              calls.push({ type: 'query', selector });
              return {
                scrollIntoView(options) {
                  calls.push({ type: 'scroll', options });
                },
              };
            },
          },
        };

        app.openScrapePreviewGallery({
          file_id: 13,
          files: [
            'EBOD-829-preview-01.jpg',
            'EBOD-829-preview-02.jpg',
            'EBOD-829-preview-03.jpg',
          ],
        }, 1);

        calls.length = 0;
        app.showNextScrapePreview();

        console.log(JSON.stringify({
          index: app.scrapePreviewGalleryIndex,
          calls,
        }));
        """
    )

    result = run_frontend_script(script)

    assert result["index"] == 2
    assert result["calls"] == [
        {"type": "query", "selector": '[data-preview-index="2"]'},
        {
            "type": "scroll",
            "options": {"behavior": "smooth", "block": "nearest", "inline": "nearest"},
        },
    ]


def test_scrape_detail_modal_markup_contains_preview_sections():
    html = (PROJECT_ROOT / "static/index.html").read_text(encoding="utf-8")

    assert "刮削内容概览" in html
    assert "封面预览" in html
    assert "生成文件" in html
    assert "重点文件" in html
    assert "预览图" in html
    assert "showScrapePreviewGallery" in html
    assert "showPreviousScrapePreview" in html
    assert "showNextScrapePreview" in html
    assert "scrape-preview-nav-icon" in html
    assert 'x-ref="scrapePreviewStrip"' in html
    assert ':data-preview-index="index"' in html
    assert "&lsaquo;" not in html
    assert "&rsaquo;" not in html


def test_scrape_detail_modal_uses_compact_layout_styles():
    css = (PROJECT_ROOT / "static/css/index.css").read_text(encoding="utf-8")

    assert ".modal.scrape-detail-modal" in css
    assert "max-width: 880px;" in css
    assert "grid-template-columns: 220px minmax(0, 1fr);" in css
    assert ".scrape-preview-gallery" in css
    assert ".scrape-preview-thumb.active" in css
    assert "padding: 10px 18px 2px;" in css
    assert "scroll-padding: 0 18px;" in css
    assert ".scrape-preview-nav-icon" in css


def test_scan_and_scrape_tables_use_separate_layout_classes():
    html = (PROJECT_ROOT / "static/index.html").read_text(encoding="utf-8")

    assert '<table class="scan-table">' in html
    assert '<table class="scrape-table">' in html


def test_scrape_controls_use_dedicated_scrape_icon_classes_without_changing_organize_icon():
    html = (PROJECT_ROOT / "static/index.html").read_text(encoding="utf-8")

    assert 'class="nav-scrape"' in html
    assert 'class="primary scrape-trigger"' in html
    assert "getUiIcon('scrape')" in html
    assert '<span class="button-icon" x-html="getUiIcon(\'organize\')"></span>' in html


def test_scrape_icon_styles_have_separate_bright_treatment():
    css = (PROJECT_ROOT / "static/css/index.css").read_text(encoding="utf-8")

    assert ".header-nav a.nav-scrape" in css
    assert "button.primary.scrape-trigger" in css
    assert ".icon-action.action-scrape" in css


def test_scrape_icons_force_svg_descendants_to_follow_current_color():
    css = (PROJECT_ROOT / "static/css/index.css").read_text(encoding="utf-8")

    assert ".header-nav .nav-icon svg *" in css
    assert ".button-icon svg *" in css
    assert ".icon-glyph svg *" in css
    assert "stroke: currentColor;" in css
    assert "fill: none;" in css


def test_scrape_icon_uses_simple_magnifier_shape():
    script = textwrap.dedent(
        """
        import fs from 'node:fs';
        import vm from 'node:vm';

        const context = vm.createContext({ console });
        context.window = context;
        context.globalThis = context;

        const source = fs.readFileSync('static/js/render.js', 'utf8');
        vm.runInContext(source, context, { filename: 'static/js/render.js' });

        const render = context.NoctraRender.createRender();
        const icon = render.getUiIcon('scrape');

        console.log(JSON.stringify({ icon }));
        """
    )

    result = run_frontend_script(script)

    assert '<circle' in result["icon"]
    assert 'cx="10.5"' in result["icon"]
    assert 'cy="10.5"' in result["icon"]
    assert 'd="M15.5 15.5L19 19"' in result["icon"]


def test_scan_table_has_compact_column_widths_for_medium_screens():
    css = (PROJECT_ROOT / "static/css/index.css").read_text(encoding="utf-8")

    assert ".scan-table" in css
    assert "min-width: 1180px;" in css
    assert ".scan-table th.col-name," in css
    assert "width: 300px;" in css
    assert ".scan-table th.col-target," in css
    assert "width: 360px;" in css
