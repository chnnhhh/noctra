(function (window) {
    function createState() {
        return {
            loading: false,
            loadingText: '正在加载...',
            error: null,
            success: null,
            files: [],
            scanFilesCache: [],
            historyFilesCache: [],
            selectedFiles: {},
            stats: {
                total_files: 0,
                identified: 0,
                unidentified: 0,
                pending: 0,
                processed: 0
            },
            scanLoaded: false,
            historyLoaded: false,
            view: 'scan', // 'scan', 'scrape', or 'history'
            currentFilter: 'all',
            sortField: 'default',
            sortDirection: 'asc',
            scrapeFilter: 'all',  // all, pending, success, failed
            scrapeSort: 'code',   // code, scrape_time
            pageSize: 50,
            pageSizeOptions: [20, 50, 100],
            currentPage: 1,
            batchJob: null,
            batchItemsIndex: {},
            batchPollTimer: null,
            batchPollingBusy: false,
            batchExpanded: false,
            batchSubmitting: false,
            batchCancelling: false,
            batchVisibleSince: 0,
            batchExpandTimer: null,
            batchExpanding: false,
            collator: new Intl.Collator('en', {
                numeric: true,
                sensitivity: 'base'
            }),
            copyToast: {
                visible: false,
                text: '路径已复制到剪贴板',
                x: 0,
                y: 0,
                placement: 'right'
            },
            copyToastTimer: null,
            activeStatusMenuId: null,
            statusHideTimer: null,
            showConfirmModal: false,
            confirmFiles: [],
            showDeleteModal: false,
            deleteTargetFile: null,
            distDir: '/dist',

            get allSelected() {
                return this.currentPageSelectableFiles.length > 0 &&
                       this.pageSelectedCount === this.currentPageSelectableFiles.length;
            },

            get hasSelected() {
                return Object.values(this.selectedFiles).some(v => v);
            },

            get selectedCount() {
                return Object.values(this.selectedFiles).filter(v => v).length;
            },

            get selectedEntries() {
                return this.scanFilesCache.filter(file => this.selectedFiles[file.id]);
            },

            get batchRunning() {
                return !!this.batchJob && ['queued', 'running'].includes(this.batchJob.status);
            },

            get batchPanelVisible() {
                return !!this.batchJob;
            },

            get batchPanelState() {
                if (!this.batchJob) {
                    return 'idle';
                }
                if (this.batchRunning || this.batchSubmitting) {
                    return 'running';
                }
                if (!this.batchExpanded) {
                    return 'collapsed';
                }
                return 'completed';
            },

            get batchCancelable() {
                return this.batchRunning &&
                       !!this.batchJob &&
                       !String(this.batchJob.id || '').startsWith('optimistic-');
            },

            get batchTerminal() {
                return !!this.batchJob && ['completed', 'failed', 'cancelled'].includes(this.batchJob.status);
            },

            get batchFailedCount() {
                return this.batchJob?.failed || 0;
            },

            get batchProgressPercent() {
                if (!this.batchJob || this.batchJob.total === 0) {
                    return 0;
                }
                return Math.max(0, Math.min(100, Math.round((this.batchJob.processed / this.batchJob.total) * 100)));
            },

            get batchProgressText() {
                if (!this.batchJob) {
                    return '';
                }
                if (this.batchJob.status === 'queued') {
                    return `批处理已创建，共 ${this.batchJob.total} 项，即将开始整理`;
                }
                if (this.batchRunning) {
                    return `正在处理 ${this.batchJob.processed} / ${this.batchJob.total}，你可以继续翻页、筛选和查看行内状态`;
                }
                if (this.batchJob.status === 'cancelled') {
                    return `任务已取消，已完成 ${this.batchJob.processed} / ${this.batchJob.total}`;
                }
                return `处理完成：成功 ${this.batchJob.succeeded}，跳过 ${this.batchJob.skipped}，失败 ${this.batchJob.failed}`;
            },

            get batchInfoLine() {
                if (!this.batchJob) {
                    return '';
                }
                if (this.batchJob.status === 'queued') {
                    return '批处理已加入队列，面板会持续显示当前任务状态，开始执行后会实时同步进度。';
                }
                if (this.batchRunning) {
                    return '系统正在按顺序处理选中的文件，表格中的对应行会实时同步到当前进度。';
                }
                if (this.batchJob.status === 'cancelled') {
                    return '批处理已取消，已完成的项目会保留结果，未完成的项目保持原有状态。';
                }
                if (this.batchJob.failed > 0) {
                    return '批量整理已结束，失败项仍保留在列表中，方便你继续筛选和处理。';
                }
                return '本批次已结束，整理结果已同步到列表和历史记录中。';
            },

            get confirmCodes() {
                const seen = new Set();
                return this.confirmFiles
                    .map(file => file.identified_code || this.getFilename(file.original_path))
                    .filter(code => {
                        if (!code || seen.has(code)) {
                            return false;
                        }
                        seen.add(code);
                        return true;
                    });
            },

            get filteredFiles() {
                if (this.currentFilter === 'all') {
                    return this.files;
                }

                const statusMap = {
                    'identified': 'identified',
                    'unidentified': 'unidentified',
                    'pending': 'pending',
                    'duplicate': 'duplicate',
                    'target_exists': 'target_exists',
                    'processed': 'processed'
                };

                return this.files.filter(f => {
                    if (this.currentFilter === 'identified') {
                        return f.identified_code && f.status !== 'processed';
                    }
                    if (this.currentFilter === 'unidentified') {
                        return !f.identified_code;
                    }
                    return f.status === statusMap[this.currentFilter];
                });
            },

            get sortFieldOptions() {
                if (this.view === 'history') {
                    return [
                        { value: 'time', label: '时间' },
                        { value: 'code', label: '番号' },
                        { value: 'status', label: '状态' }
                    ];
                }

                return [
                    { value: 'default', label: '默认排序' },
                    { value: 'code', label: '番号' },
                    { value: 'status', label: '状态' }
                ];
            },

            get sortedFiles() {
                const files = [...this.filteredFiles];
                return files.sort((a, b) => this.compareSort(a, b));
            },

            get totalPages() {
                return Math.max(1, Math.ceil(this.sortedFiles.length / this.pageSize));
            },

            get currentPageValue() {
                return Math.min(this.currentPage, this.totalPages);
            },

            get pageRangeStart() {
                if (this.sortedFiles.length === 0) {
                    return 0;
                }
                return ((this.currentPageValue - 1) * this.pageSize) + 1;
            },

            get pageRangeEnd() {
                if (this.sortedFiles.length === 0) {
                    return 0;
                }
                return Math.min(this.pageRangeStart + this.pageSize - 1, this.sortedFiles.length);
            },

            get paginatedFiles() {
                const start = (this.currentPageValue - 1) * this.pageSize;
                return this.sortedFiles.slice(start, start + this.pageSize);
            },

            get currentPageSelectableFiles() {
                return this.paginatedFiles.filter(file => this.canSelectFile(file));
            },

            get pageSelectedCount() {
                return this.currentPageSelectableFiles.filter(file => this.selectedFiles[file.id]).length;
            },

            get pageSelectionState() {
                if (this.pageSelectedCount === 0) {
                    return 'none';
                }
                if (this.pageSelectedCount === this.currentPageSelectableFiles.length) {
                    return 'all';
                }
                return 'partial';
            },

            get paginationItems() {
                const total = this.totalPages;
                const current = this.currentPageValue;

                if (total <= 7) {
                    return Array.from({ length: total }, (_, index) => ({
                        key: `page-${index + 1}`,
                        page: index + 1
                    }));
                }

                const pages = [1];
                if (current > 3) {
                    pages.push(null);
                }

                for (let page = Math.max(2, current - 1); page <= Math.min(total - 1, current + 1); page += 1) {
                    pages.push(page);
                }

                if (current < total - 2) {
                    pages.push(null);
                }

                pages.push(total);

                return pages.map((page, index) => ({
                    key: page === null ? `gap-${index}` : `page-${page}`,
                    page
                }));
            },
        };
    }

    window.NoctraState = {
        createState
    };
})(window);
