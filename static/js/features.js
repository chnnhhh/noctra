(function (window) {
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
                if (viewName === 'history') {
                    this.sortField = 'time';
                    this.sortDirection = 'desc';
                    return;
                }

                this.sortField = 'default';
                this.sortDirection = 'asc';
            },

            setPageSize(size) {
                this.pageSize = Number(size);
                this.currentPage = 1;
                this.closeStatusMenu();
            },

            goToPage(page) {
                const nextPage = Math.max(1, Math.min(this.totalPages, page));
                this.currentPage = nextPage;
                this.closeStatusMenu();
            },

            setBatchJob(job) {
                const previousStatus = this.batchJob?.status;
                this.batchJob = job;
                const index = {};
                (job?.items || []).forEach(item => {
                    index[item.id] = item;
                });
                this.batchItemsIndex = index;
                if (!job) {
                    this.batchExpanded = false;
                    return;
                }

                if (['queued', 'running'].includes(job.status)) {
                    this.batchExpanded = true;
                } else if (['queued', 'running'].includes(previousStatus) && ['completed', 'failed', 'cancelled'].includes(job.status)) {
                    this.batchExpanded = false;
                } else if (!previousStatus && ['completed', 'failed', 'cancelled'].includes(job.status)) {
                    this.batchExpanded = false;
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
            },

            async refreshAfterBatchCompletion() {
                const preservedFilter = this.currentFilter;
                const preservedPage = this.currentPage;

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
                    this.currentFilter = preservedFilter;
                    this.currentPage = preservedPage;
                    this.historyLoaded = false;
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
                    try {
                        await this.fetchBatchJob(batchId, { syncAfterDone: true });
                    } catch (error) {
                        this.stopBatchPolling();
                        this.batchSubmitting = false;
                        this.batchCancelling = false;
                        this.error = '批处理状态获取失败：' + error.message;
                    }
                }, 800);
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
                this.files = this.view === 'history' ? this.historyFilesCache : this.scanFilesCache;
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

                if (viewName === 'scan') {
                    if (!this.scanLoaded) {
                        await this.scanFiles();
                        return;
                    }
                } else if (!this.historyLoaded) {
                    await this.loadHistory();
                    return;
                }

                this.switchVisibleFiles();
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

            async loadHistory() {
                this.loading = true;
                this.loadingText = '正在加载历史记录...';
                this.error = null;
                this.success = null;
                this.currentFilter = 'all';

                try {
                    const response = await fetch('/api/history');
                    const data = await response.json();

                    this.updateStats(data);
                    this.historyFilesCache = data.files.filter(file => file.status === 'processed');
                    this.files = this.historyFilesCache;
                    this.historyLoaded = true;
                    this.selectedFiles = {};
                    this.confirmFiles = [];
                    this.currentPage = 1;
                    this.closeStatusMenu();
                    this.view = 'history';
                } catch (e) {
                    this.error = '加载历史失败: ' + e.message;
                } finally {
                    this.loading = false;
                }
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

            async executeOrganize() {
                this.showConfirmModal = false;
                this.batchSubmitting = true;
                this.error = null;
                this.success = null;

                const fileIds = this.confirmFiles.map(file => file.id);

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

                    this.selectedFiles = {};
                    this.batchExpanded = true;
                    this.setBatchJob(batchJob);
                    this.startBatchPolling(batchJob.id);
                    this.success = '已启动批量整理任务';
                } catch (e) {
                    if (e.message === '所选文件状态已变化，请刷新列表后重试' || e.message === '没有可整理的待处理文件') {
                        await this.scanFiles(true);
                        this.clearSelection();
                        this.error = '所选文件状态已变化，列表已自动刷新，请重新选择待处理项';
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
                if (!this.batchJob || !this.batchRunning) {
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
                    this.historyLoaded = false;
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

            init() {
                this.scanFiles();
            },

            destroy() {
                this.stopBatchPolling();
            }
        };
    }

    window.NoctraFeatures = {
        createFeatures
    };
})(window);
