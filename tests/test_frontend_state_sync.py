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
