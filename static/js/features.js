(function (window) {
    const MIN_VISIBLE = 800;
    const BATCH_PANEL_ANIMATION_MS = 280;
    const OPTIMISTIC_BATCH_PREFIX = 'optimistic-';
    const SCRAPE_LIST_FETCH_SIZE = 200;

    function createFeatures() {
        return {
            showStatusMenu(fileId) {
                if (this.statusHideTimer) {
                    clearTimeout(this.statusHideTimer);
                    this.statusHideTimer = null;
                }
                this.activeStatusMenuId = fileId;
            },

            scheduleStatusMenuHide(fileId) {
                if (this.statusHideTimer) {
                    clearTimeout(this.statusHideTimer);
                }

                this.statusHideTimer = setTimeout(() => {
                    if (this.activeStatusMenuId === fileId) {
                        this.activeStatusMenuId = null;
                    }
                    this.statusHideTimer = null;
                }, 300);
            },

            closeStatusMenu() {
                if (this.statusHideTimer) {
                    clearTimeout(this.statusHideTimer);
                    this.statusHideTimer = null;
                }
                this.activeStatusMenuId = null;
            },

            handleStatusAction(file, actionKey) {
                this.closeStatusMenu();

                if (actionKey === 'organize') {
                    this.confirmFiles = [file];
                    this.showConfirmModal = true;
                    return;
                }

                if (actionKey === 'delete') {
                    this.openDeleteModal(file);
                }
            },

            setFilter(filter) {
                this.currentFilter = filter;
                this.currentPage = 1;
                this.closeStatusMenu();
            },

            setSortField(field) {
                this.sortField = field;
                this.currentPage = 1;
                this.closeStatusMenu();
            },

            toggleSortDirection() {
                if (this.view === 'scan' && this.sortField === 'default') {
                    return;
                }
                this.sortDirection = this.sortDirection === 'desc' ? 'asc' : 'desc';
                this.currentPage = 1;
                this.closeStatusMenu();
            },

            resetSortForView(viewName = this.view) {
                if (viewName === 'scrape') {
                    return;
                }
                this.sortField = 'default';
                this.sortDirection = 'asc';
            },

            setPageSize(size) {
                this.pageSize = Number(size);
                if (this.view === 'scrape') {
                    this.scrapePage = 1;
                } else {
                    this.currentPage = 1;
                }
                this.closeStatusMenu();
            },

            goToPage(page) {
                const nextPage = Math.max(1, Math.min(this.totalPages, page));
                this.currentPage = nextPage;
                this.closeStatusMenu();
            },

            createOptimisticBatchJob(files) {
                const now = new Date().toISOString();
                return {
                    id: `${OPTIMISTIC_BATCH_PREFIX}${Date.now()}`,
                    status: 'queued',
                    total: files.length,
                    processed: 0,
                    succeeded: 0,
                    skipped: 0,
                    failed: 0,
                    created_at: now,
                    started_at: null,
                    finished_at: null,
                    items: files.map(file => ({
                        id: file.id,
                        code: file.identified_code,
                        source_path: file.original_path,
                        target_path: file.target_path,
                        status: 'pending',
                        message: null,
                        started_at: null,
                        finished_at: null
                    }))
                };
            },

            animateBatchPanelExpand() {
                if (this.batchExpandTimer) {
                    clearTimeout(this.batchExpandTimer);
                }

                this.batchExpanding = true;
                this.batchExpandTimer = setTimeout(() => {
                    this.batchExpanding = false;
                    this.batchExpandTimer = null;
                }, BATCH_PANEL_ANIMATION_MS);
            },

            async ensureBatchMinimumVisibility() {
                if (!this.batchVisibleSince) {
                    return;
                }

                const elapsed = Date.now() - this.batchVisibleSince;
                if (elapsed < MIN_VISIBLE) {
                    await new Promise(resolve => setTimeout(resolve, MIN_VISIBLE - elapsed));
                }
            },

            setBatchJob(job) {
                this.batchJob = job;
                const index = {};
                (job?.items || []).forEach(item => {
                    index[item.id] = item;
                });
                this.batchItemsIndex = index;
                if (!job) {
                    this.batchExpanded = false;
                    this.batchVisibleSince = 0;
                    this.batchPollingBusy = false;
                    if (this.batchExpandTimer) {
                        clearTimeout(this.batchExpandTimer);
                        this.batchExpandTimer = null;
                    }
                    this.batchExpanding = false;
                }
            },

            toggleBatchExpanded() {
                if (!this.batchJob) {
                    return;
                }
                this.batchExpanded = !this.batchExpanded;
            },

            clearBatchJob() {
                this.stopBatchPolling();
                this.setBatchJob(null);
                this.batchSubmitting = false;
                this.batchCancelling = false;
            },

            stopBatchPolling() {
                if (this.batchPollTimer) {
                    clearInterval(this.batchPollTimer);
                    this.batchPollTimer = null;
                }
                this.batchPollingBusy = false;
            },

            async refreshAfterBatchCompletion() {
                const preservedFilter = this.currentFilter;
                const preservedPage = this.currentPage;
                const hiddenAfterProcessed = ['identified', 'pending', 'duplicate', 'target_exists'];

                try {
                    const response = await fetch('/api/scan');
                    const data = await response.json();
                    if (!response.ok) {
                        throw new Error(data.detail || '刷新扫描结果失败');
                    }

                    this.updateStats(data);
                    this.scanFilesCache = data.files;
                    this.files = data.files;
                    this.scanLoaded = true;
                    this.selectedFiles = {};
                    this.confirmFiles = [];
                    this.closeStatusMenu();
                    this.view = 'scan';
                    this.distDir = '/dist';
                    this.scrapeLoaded = false;
                    this.scrapeSelectedFiles = {};
                    this.scrapePage = 1;
                    this.currentFilter = hiddenAfterProcessed.includes(preservedFilter) ? 'all' : preservedFilter;
                    this.currentPage = this.currentFilter === preservedFilter ? preservedPage : 1;
                } catch (error) {
                    this.error = '刷新扫描结果失败：' + error.message;
                }
            },

            async fetchBatchJob(batchId, { syncAfterDone = false } = {}) {
                const response = await fetch(`/api/batches/${batchId}`);
                const batchJob = await response.json();

                if (!response.ok) {
                    throw new Error(batchJob.detail || '获取批处理状态失败');
                }

                if (['completed', 'failed', 'cancelled'].includes(batchJob.status)) {
                    await this.ensureBatchMinimumVisibility();
                }

                this.setBatchJob(batchJob);

                if (['completed', 'failed', 'cancelled'].includes(batchJob.status)) {
                    this.stopBatchPolling();
                    this.batchSubmitting = false;
                    this.batchCancelling = false;
                    if (syncAfterDone) {
                        await this.refreshAfterBatchCompletion();
                    }
                }
            },

            startBatchPolling(batchId) {
                this.stopBatchPolling();
                this.batchPollTimer = setInterval(async () => {
                    if (this.batchPollingBusy) {
                        return;
                    }

                    this.batchPollingBusy = true;
                    try {
                        await this.fetchBatchJob(batchId, { syncAfterDone: true });
                    } catch (error) {
                        this.stopBatchPolling();
                        this.batchSubmitting = false;
                        this.batchCancelling = false;
                        this.error = '批处理状态获取失败：' + error.message;
                    } finally {
                        this.batchPollingBusy = false;
                    }
                }, 200);
            },

            updateStats(data) {
                this.stats = {
                    total_files: data.total_files,
                    identified: data.identified,
                    unidentified: data.unidentified,
                    pending: data.pending,
                    processed: data.processed
                };
            },

            switchVisibleFiles() {
                this.files = this.scanFilesCache;
                this.selectedFiles = {};
                this.currentPage = 1;
                this.closeStatusMenu();
            },

            async switchView(viewName) {
                this.view = viewName;
                this.resetSortForView(viewName);
                this.currentFilter = 'all';
                this.error = null;
                this.success = null;

                if (viewName !== 'scrape') {
                    this.closeScrapeDetail();
                }

                if (viewName === 'scrape') {
                    if (!this.scrapeLoaded) {
                        await this.loadScrapeFiles();
                        return;
                    }
                    return;
                }

                if (!this.scanLoaded) {
                    await this.scanFiles();
                    return;
                }

                this.files = this.scanFilesCache;
                this.selectedFiles = {};
                this.currentPage = 1;
                this.closeStatusMenu();
            },

            async scanFiles(forceRescan = false) {
                this.loading = true;
                this.loadingText = '正在扫描目录...';
                this.error = null;
                if (!this.batchRunning && !this.batchSubmitting) {
                    this.success = null;
                }
                this.currentFilter = 'all';

                try {
                    const scanUrl = forceRescan ? '/api/scan?force_rescan=true' : '/api/scan';
                    const response = await fetch(scanUrl);
                    const data = await response.json();

                    this.updateStats(data);
                    this.scanFilesCache = data.files;
                    this.files = data.files;
                    this.scanLoaded = true;
                    this.selectedFiles = {};
                    this.confirmFiles = [];
                    this.currentPage = 1;
                    this.closeStatusMenu();
                    this.view = 'scan';
                    this.distDir = '/dist'; // 默认值
                } catch (e) {
                    this.error = '扫描失败: ' + e.message;
                } finally {
                    this.loading = false;
                }
            },

            normalizeScrapeFile(item) {
                return {
                    id: item.file_id,
                    identified_code: item.code,
                    target_path: item.target_path || '',
                    scrape_status: item.scrape_status || 'pending',
                    last_scrape_at: item.last_scrape_at || null,
                    original_path: item.original_path || '',
                    status: item.status || 'processed',
                    scrape_started_at: item.scrape_started_at || null,
                    scrape_finished_at: item.scrape_finished_at || null,
                    scrape_stage: item.scrape_stage || null,
                    scrape_source: item.scrape_source || null,
                    scrape_error: item.scrape_error || null,
                    scrape_error_user_message: item.scrape_error_user_message || null,
                    scrape_logs: item.scrape_logs || []
                };
            },

            normalizeScrapeDetailPayload(detail, fallbackCode = '') {
                const metadata = detail?.metadata || {};
                return {
                    file_id: detail?.file_id || null,
                    code: detail?.code || fallbackCode || '',
                    poster_url: detail?.poster_url || null,
                    files: Array.isArray(detail?.files) ? detail.files : [],
                    metadata: {
                        code: metadata.code || detail?.code || fallbackCode || '',
                        plot: metadata.plot || '',
                        actors: Array.isArray(metadata.actors) ? metadata.actors : [],
                        release_date: metadata.release_date || '',
                        runtime: metadata.runtime || '',
                        tags: Array.isArray(metadata.tags) ? metadata.tags : []
                    }
                };
            },

            async fetchAllScrapeListData() {
                const firstPage = await ScrapeAPI.getList({
                    page: 1,
                    perPage: SCRAPE_LIST_FETCH_SIZE
                });
                const items = [...(firstPage.items || [])];
                const total = Number(firstPage.total || items.length);
                const totalPages = Math.max(1, Math.ceil(total / SCRAPE_LIST_FETCH_SIZE));

                for (let page = 2; page <= totalPages; page += 1) {
                    const nextPage = await ScrapeAPI.getList({
                        page,
                        perPage: SCRAPE_LIST_FETCH_SIZE
                    });
                    items.push(...(nextPage.items || []));
                }

                return {
                    ...firstPage,
                    items
                };
            },

            async loadScrapeFiles() {
                this.loading = true;
                this.loadingText = '正在加载刮削列表...';
                this.error = null;
                this.success = null;

                try {
                    const data = await this.fetchAllScrapeListData();

                    this.scrapeFilesCache = (data.items || []).map(item => this.normalizeScrapeFile(item));

                    const activeJob = data.active_job || null;
                    if (activeJob) {
                        this.setScrapeBatchJob(activeJob);
                        this.scrapeBatchExpanded = true;
                        if (['queued', 'running'].includes(activeJob.status)) {
                            this.startScrapeBatchPolling(activeJob.id);
                        }
                    } else {
                        this.stopScrapeBatchPolling();
                        this.setScrapeBatchJob(null);
                        this.scrapeBatchExpanded = false;
                        this.scrapeBatchCancelling = false;
                    }

                    this.scrapeLoaded = true;
                    this.scrapeSelectedFiles = {};
                    this.scrapePage = 1;
                    this.closeStatusMenu();
                } catch (e) {
                    this.error = '加载刮削列表失败: ' + e.message;
                } finally {
                    this.loading = false;
                }
            },

            setScrapeFilter(filter) {
                this.scrapeFilter = filter;
                this.scrapePage = 1;
                this.closeStatusMenu();
            },

            setScrapeSortField(field) {
                this.scrapeSortField = field;
                this.scrapePage = 1;
                this.closeStatusMenu();
            },

            toggleScrapeSortDirection() {
                this.scrapeSortDirection = this.scrapeSortDirection === 'desc' ? 'asc' : 'desc';
                this.scrapePage = 1;
                this.closeStatusMenu();
            },

            setScrapeFileSelected(file, checked) {
                if (!this.canSelectScrapeFile(file)) return;
                const next = { ...this.scrapeSelectedFiles };
                if (checked) { next[file.id] = true; } else { delete next[file.id]; }
                this.scrapeSelectedFiles = next;
            },

            toggleScrapeFileSelection(file) {
                if (!this.canSelectScrapeFile(file)) return;
                this.setScrapeFileSelected(file, !this.scrapeSelectedFiles[file.id]);
            },

            toggleScrapeCurrentPageSelection(forceChecked = null) {
                const shouldSelect = forceChecked === null ? this.scrapePageSelectionState !== 'all' : forceChecked;
                const next = { ...this.scrapeSelectedFiles };
                this.scrapeCurrentPageSelectableFiles.forEach(file => {
                    if (shouldSelect) { next[file.id] = true; } else { delete next[file.id]; }
                });
                this.scrapeSelectedFiles = next;
            },

            clearScrapeSelection() {
                this.scrapeSelectedFiles = {};
            },

            async confirmBatchScrape() {
                const entries = this.scrapeSelectedEntries.filter(file => this.canSelectScrapeFile(file));
                if (entries.length === 0) {
                    return;
                }
                await this.executeScrapeBatch(entries);
            },

            goToScrapePage(page) {
                const nextPage = Math.max(1, Math.min(this.scrapeTotalPages, page));
                this.scrapePage = nextPage;
                this.closeStatusMenu();
            },

            confirmOrganize() {
                if (this.batchRunning || this.batchSubmitting) {
                    return;
                }

                this.confirmFiles = this.selectedEntries.filter(file => this.canSelectFile(file));

                if (this.confirmFiles.length === 0) {
                    return;
                }

                this.showConfirmModal = true;
            },

            openDeleteModal(file) {
                this.closeStatusMenu();
                this.deleteTargetFile = file;
                this.showDeleteModal = true;
            },

            closeDeleteModal() {
                this.showDeleteModal = false;
                this.deleteTargetFile = null;
            },

            showScrapeErrorDetails(file) {
                const liveItem = this.scrapeBatchItemsIndex[file.id] || null;
                this.scrapeErrorFile = liveItem ? {
                    ...file,
                    scrape_stage: liveItem.stage || file.scrape_stage || null,
                    scrape_source: liveItem.source || file.scrape_source || null,
                    scrape_error: liveItem.technical_error || file.scrape_error || null,
                    scrape_error_user_message: liveItem.user_message || file.scrape_error_user_message || null,
                    scrape_logs: (file.scrape_logs && file.scrape_logs.length > 0)
                        ? file.scrape_logs
                        : ((this.scrapeBatchJob?.current_file_id === file.id)
                            ? (this.scrapeBatchJob?.recent_logs || [])
                            : [])
                } : file;
                this.showScrapeErrorModal = true;
            },

            async showScrapeDetail(file) {
                if (!file?.id) {
                    return;
                }

                this.closeStatusMenu();
                this.scrapeDetailLoading = true;
                this.showScrapeDetailModal = true;
                this.scrapeDetailFile = this.normalizeScrapeDetailPayload(null, file.identified_code || '');

                try {
                    const detail = await ScrapeAPI.getDetail(file.id);
                    this.scrapeDetailFile = this.normalizeScrapeDetailPayload(detail, file.identified_code || '');
                } catch (error) {
                    this.showScrapeDetailModal = false;
                    this.scrapeDetailFile = null;
                    this.error = '加载刮削内容失败: ' + error.message;
                } finally {
                    this.scrapeDetailLoading = false;
                }
            },

            closeScrapeDetail() {
                this.showScrapeDetailModal = false;
                this.scrapeDetailLoading = false;
                this.scrapeDetailFile = null;
                this.closeScrapePosterPreview();
                this.closeScrapePreviewGallery();
            },

            openScrapePosterPreview(url) {
                if (!url) {
                    return;
                }
                this.scrapeDetailPosterPreview = url;
                this.showScrapePosterModal = true;
            },

            closeScrapePosterPreview() {
                this.showScrapePosterModal = false;
                this.scrapeDetailPosterPreview = null;
            },

            openScrapePreviewGallery(detail, startIndex = 0) {
                const previewFiles = this.getScrapeDetailArtifacts(detail).previewFiles || [];
                if (previewFiles.length === 0) {
                    return;
                }

                const nextIndex = Math.max(0, Math.min(startIndex, previewFiles.length - 1));
                this.scrapePreviewGalleryImages = previewFiles;
                this.scrapePreviewGalleryIndex = nextIndex;
                this.showScrapePreviewGalleryModal = true;
                this.syncCurrentScrapePreviewThumb();
            },

            closeScrapePreviewGallery() {
                this.showScrapePreviewGalleryModal = false;
                this.scrapePreviewGalleryImages = [];
                this.scrapePreviewGalleryIndex = 0;
            },

            selectScrapePreview(index) {
                if (index < 0 || index >= this.scrapePreviewGalleryImages.length) {
                    return;
                }
                this.scrapePreviewGalleryIndex = index;
                this.syncCurrentScrapePreviewThumb();
            },

            showPreviousScrapePreview() {
                if (!this.canShowPreviousScrapePreview) {
                    return;
                }
                this.scrapePreviewGalleryIndex -= 1;
                this.syncCurrentScrapePreviewThumb();
            },

            showNextScrapePreview() {
                if (!this.canShowNextScrapePreview) {
                    return;
                }
                this.scrapePreviewGalleryIndex += 1;
                this.syncCurrentScrapePreviewThumb();
            },

            syncCurrentScrapePreviewThumb() {
                const runAfterRender = typeof this.$nextTick === 'function'
                    ? this.$nextTick.bind(this)
                    : (callback) => callback();

                runAfterRender(() => {
                    const strip = this.$refs?.scrapePreviewStrip;
                    if (!strip || typeof strip.querySelector !== 'function') {
                        return;
                    }

                    const thumb = strip.querySelector(`[data-preview-index="${this.scrapePreviewGalleryIndex}"]`);
                    if (!thumb || typeof thumb.scrollIntoView !== 'function') {
                        return;
                    }

                    thumb.scrollIntoView({
                        behavior: 'smooth',
                        block: 'nearest',
                        inline: 'nearest'
                    });
                });
            },

            async executeOrganize() {
                this.showConfirmModal = false;
                this.batchSubmitting = true;
                this.error = null;
                this.success = null;

                const selectedFiles = [...this.confirmFiles];
                const fileIds = selectedFiles.map(file => file.id);
                this.selectedFiles = {};
                this.batchVisibleSince = Date.now();
                this.batchExpanded = true;
                this.animateBatchPanelExpand();
                this.setBatchJob(this.createOptimisticBatchJob(selectedFiles));

                try {
                    const response = await fetch('/api/batches', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ file_ids: fileIds })
                    });
                    const batchJob = await response.json();

                    if (!response.ok) {
                        throw new Error(batchJob.detail || '创建批处理任务失败');
                    }

                    this.setBatchJob(batchJob);
                    this.startBatchPolling(batchJob.id);
                } catch (e) {
                    if (this.batchJob && String(this.batchJob.id || '').startsWith(OPTIMISTIC_BATCH_PREFIX)) {
                        this.clearBatchJob();
                    }
                    if (e.message === '所选文件状态已变化，请刷新列表后重试' || e.message === '没有可整理的文件') {
                        await this.scanFiles(true);
                        this.clearSelection();
                        this.error = '所选文件状态已变化，列表已自动刷新，请重新选择可整理项';
                    } else {
                        this.error = '整理失败: ' + e.message;
                    }
                } finally {
                    this.confirmFiles = [];
                    if (!this.batchJob || ['completed', 'failed', 'cancelled'].includes(this.batchJob.status)) {
                        this.batchSubmitting = false;
                    }
                }
            },

            async cancelBatch() {
                if (!this.batchCancelable) {
                    return;
                }

                this.batchCancelling = true;
                this.error = null;

                try {
                    const response = await fetch(`/api/batches/${this.batchJob.id}/cancel`, {
                        method: 'POST'
                    });
                    const data = await response.json();
                    if (!response.ok) {
                        throw new Error(data.detail || '取消批处理失败');
                    }
                    this.success = data.message;
                } catch (e) {
                    this.error = '取消失败: ' + e.message;
                    this.batchCancelling = false;
                }
            },

            async executeDelete(action) {
                if (!this.deleteTargetFile) {
                    return;
                }

                this.loading = true;
                this.loadingText = action === 'delete_source' ? '正在删除原始文件...' : '正在忽略扫描记录...';
                this.error = null;
                this.success = null;
                const fileId = this.deleteTargetFile.id;
                this.closeDeleteModal();

                try {
                    const response = await fetch(`/api/files/${fileId}/delete`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ action })
                    });
                    const data = await response.json();

                    if (!response.ok) {
                        throw new Error(data.detail || '删除失败');
                    }

                    this.success = data.message;
                    await this.scanFiles();
                } catch (e) {
                    this.error = '删除失败: ' + e.message;
                } finally {
                    this.loading = false;
                }
            },

            getDeleteModalDescription() {
                if (!this.deleteTargetFile) {
                    return '请选择处理方式：';
                }

                if (this.deleteTargetFile.status === 'target_exists') {
                    return '已存在于目标目录中。请选择处理方式：';
                }

                if (this.deleteTargetFile.status === 'skipped') {
                    return '当前文件未识别到番号。请选择处理方式：';
                }

                return '请选择处理方式：';
            },

            setFileSelected(file, checked) {
                if (!this.canSelectFile(file)) {
                    return;
                }

                const nextSelected = { ...this.selectedFiles };
                if (checked) {
                    nextSelected[file.id] = true;
                } else {
                    delete nextSelected[file.id];
                }
                this.selectedFiles = nextSelected;
            },

            toggleFileSelection(file) {
                if (!this.canSelectFile(file)) {
                    return;
                }

                this.setFileSelected(file, !this.selectedFiles[file.id]);
            },

            toggleCurrentPageSelection(forceChecked = null) {
                const shouldSelect = forceChecked === null ? this.pageSelectionState !== 'all' : forceChecked;
                const nextSelected = { ...this.selectedFiles };

                this.currentPageSelectableFiles.forEach(file => {
                    if (shouldSelect) {
                        nextSelected[file.id] = true;
                    } else {
                        delete nextSelected[file.id];
                    }
                });

                this.selectedFiles = nextSelected;
            },

            clearSelection() {
                this.selectedFiles = {};
            },

            // ========== Scrape Batch Methods ==========

            toggleScrapeBatchExpanded() {
                if (!this.scrapeBatchJob) {
                    return;
                }
                this.scrapeBatchExpanded = !this.scrapeBatchExpanded;
            },

            animateScrapeBatchPanelExpand() {
                if (this.scrapeBatchExpandTimer) {
                    clearTimeout(this.scrapeBatchExpandTimer);
                }

                this.scrapeBatchExpanding = true;
                this.scrapeBatchExpandTimer = setTimeout(() => {
                    this.scrapeBatchExpanding = false;
                    this.scrapeBatchExpandTimer = null;
                }, BATCH_PANEL_ANIMATION_MS);
            },

            async ensureScrapeBatchMinimumVisibility() {
                if (!this.scrapeBatchVisibleSince) {
                    return;
                }

                const elapsed = Date.now() - this.scrapeBatchVisibleSince;
                if (elapsed < MIN_VISIBLE) {
                    await new Promise(resolve => setTimeout(resolve, MIN_VISIBLE - elapsed));
                }
            },

            setScrapeBatchJob(job) {
                this.scrapeBatchJob = job;
                const index = {};
                (job?.items || []).forEach(item => {
                    index[item.id] = item;
                });
                this.scrapeBatchItemsIndex = index;
                if (job) {
                    this.scrapeBatchVisibleSince = Date.now();
                } else {
                    this.scrapeBatchItemsIndex = {};
                    this.scrapeBatchPollingBusy = false;
                }
            },

            stopScrapeBatchPolling() {
                if (this.scrapeBatchPollTimer) {
                    clearInterval(this.scrapeBatchPollTimer);
                    this.scrapeBatchPollTimer = null;
                }
                this.scrapeBatchPollingBusy = false;
            },

            async fetchScrapeBatchJob(jobId, { syncAfterDone = false } = {}) {
                const job = await ScrapeAPI.getJob(jobId);

                if (['completed', 'failed', 'cancelled'].includes(job.status)) {
                    await this.ensureScrapeBatchMinimumVisibility();
                }

                this.setScrapeBatchJob(job);

                if (['completed', 'failed', 'cancelled'].includes(job.status)) {
                    this.stopScrapeBatchPolling();
                    this.scrapeBatchSubmitting = false;
                    this.scrapeBatchCancelling = false;
                    if (syncAfterDone) {
                        await this.loadScrapeFiles();
                    }
                }
            },

            startScrapeBatchPolling(jobId) {
                this.stopScrapeBatchPolling();
                this.scrapeBatchPollTimer = setInterval(async () => {
                    if (this.scrapeBatchPollingBusy) {
                        return;
                    }

                    this.scrapeBatchPollingBusy = true;
                    try {
                        await this.fetchScrapeBatchJob(jobId, { syncAfterDone: true });
                    } catch (error) {
                        this.stopScrapeBatchPolling();
                        this.scrapeBatchSubmitting = false;
                        this.scrapeBatchCancelling = false;
                        this.error = '刮削任务状态获取失败: ' + error.message;
                    } finally {
                        this.scrapeBatchPollingBusy = false;
                    }
                }, 400);
            },

            async executeScrapeBatch(files) {
                const entries = (files || []).filter(Boolean);
                if (entries.length === 0) {
                    return;
                }

                const fileIds = entries.map(file => file.id);
                this.scrapeBatchSubmitting = true;
                this.error = null;
                this.success = null;
                this.scrapeBatchVisibleSince = Date.now();
                this.scrapeBatchExpanded = true;
                this.animateScrapeBatchPanelExpand();
                this.setScrapeBatchJob(this.createOptimisticScrapeBatchJob(entries));

                try {
                    const job = await ScrapeAPI.createJob(fileIds);
                    this.setScrapeBatchJob(job);
                    this.startScrapeBatchPolling(job.id);
                } catch (e) {
                    if (this.scrapeBatchJob && String(this.scrapeBatchJob.id || '').startsWith(OPTIMISTIC_BATCH_PREFIX)) {
                        this.setScrapeBatchJob(null);
                    }
                    if (e.message === '已有刮削任务正在运行，请等待当前任务完成') {
                        await this.loadScrapeFiles();
                    }
                    this.error = '创建刮削任务失败: ' + e.message;
                    this.scrapeBatchSubmitting = false;
                    this.scrapeBatchCancelling = false;
                } finally {
                    this.scrapeSelectedFiles = {};
                }
            },

            createOptimisticScrapeBatchJob(files) {
                const now = new Date().toISOString();
                return {
                    id: `${OPTIMISTIC_BATCH_PREFIX}scrape-${Date.now()}`,
                    status: 'queued',
                    total: files.length,
                    processed: 0,
                    succeeded: 0,
                    failed: 0,
                    created_at: now,
                    started_at: null,
                    finished_at: null,
                    current_file_id: null,
                    current_file_code: null,
                    current_stage: null,
                    current_source: null,
                    current_progress_percent: 0,
                    recent_logs: [],
                    items: files.map(file => ({
                        id: file.id,
                        code: file.identified_code,
                        target_path: file.target_path,
                        status: 'pending',
                        stage: null,
                        source: null,
                        progress_percent: 0,
                        user_message: null,
                        technical_error: null,
                        started_at: null,
                        finished_at: null
                    }))
                };
            },

            async handleScrapeAction(file) {
                this.closeStatusMenu();
                await this.executeScrapeBatch([file]);
            },

            async confirmScrapeSelected() {
                const selectedFiles = this.scrapeSelectedEntries.filter(file => this.canSelectScrapeFile(file));
                if (selectedFiles.length === 0) {
                    return;
                }

                await this.executeScrapeBatch(selectedFiles);
            },

            async cancelScrapeBatch() {
                if (!this.scrapeBatchCancelable) {
                    return;
                }

                this.scrapeBatchCancelling = true;
                this.error = null;

                try {
                    const result = await ScrapeAPI.cancelJob(this.scrapeBatchJob.id);
                    this.success = result.message;
                } catch (e) {
                    this.error = '取消刮削任务失败: ' + e.message;
                    this.scrapeBatchCancelling = false;
                }
            },

            init() {
                this.scanFiles();
            },

            destroy() {
                this.stopBatchPolling();
                this.stopScrapeBatchPolling();
                if (this.batchExpandTimer) {
                    clearTimeout(this.batchExpandTimer);
                    this.batchExpandTimer = null;
                }
                if (this.scrapeBatchExpandTimer) {
                    clearTimeout(this.scrapeBatchExpandTimer);
                    this.scrapeBatchExpandTimer = null;
                }
            }
        };
    }

    window.NoctraFeatures = {
        createFeatures
    };
})(window);
