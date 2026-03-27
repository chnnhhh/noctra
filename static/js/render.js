(function (window) {
    function createRender() {
        return {
            getBadgeClass(file) {
                const batchItem = this.getBatchItem(file);
                if (batchItem) {
                    return this.getBatchBadgeClass(batchItem.status);
                }

                if (!file.identified_code) {
                    return 'unidentified';
                }
                return file.status || 'skipped';
            },

            getStatusText(status) {
                const map = {
                    'pending': '待整理',
                    'duplicate': '重复',
                    'target_exists': '已存在',
                    'processed': '已整理',
                    'scraped': '已刮削',
                    'skipped': '未识别',
                    'failed': '失败'
                };
                return map[status] || status;
            },

            getBatchJobStatusLabel(status) {
                const map = {
                    queued: 'QUEUED',
                    running: 'RUNNING',
                    completed: 'COMPLETED',
                    failed: 'FAILED',
                    cancelled: 'CANCELLED'
                };
                return map[status] || status;
            },

            getScrapeBatchJobStatusLabel(status) {
                const map = {
                    queued: 'QUEUED',
                    running: 'RUNNING',
                    completed: 'COMPLETED',
                    failed: 'FAILED',
                    cancelled: 'CANCELLED'
                };
                return map[status] || status || 'PENDING';
            },

            getScrapeBatchItemStatusText(status) {
                const map = {
                    pending: '待刮削',
                    processing: '刮削中',
                    success: '已刮削',
                    failed: '刮削失败'
                };
                return map[status] || status || '-';
            },

            getScrapeBatchBadgeClass(status) {
                const map = {
                    processing: 'processing',
                    success: 'processed',
                    failed: 'failed',
                    pending: 'pending'
                };
                return map[status] || 'pending';
            },

            getBatchItemStatusText(status) {
                const map = {
                    pending: '待整理',
                    processing: '处理中',
                    success: '已整理',
                    skipped: '已跳过',
                    failed: '失败'
                };
                return map[status] || status;
            },

            getBatchBadgeClass(status) {
                const map = {
                    processing: 'processing',
                    success: 'success',
                    skipped: 'batch_skipped',
                    failed: 'failed',
                    pending: 'pending'
                };
                return map[status] || 'pending';
            },

            getDisplayStatusText(file) {
                const batchItem = this.getBatchItem(file);
                if (batchItem) {
                    return this.getBatchItemStatusText(batchItem.status);
                }
                return this.getStatusText(file.status);
            },

            getScrapeStatusText(file) {
                const batchItem = this.getScrapeBatchItem(file);
                if (batchItem) {
                    return this.getScrapeBatchItemStatusText(batchItem.status);
                }

                const map = {
                    'pending': '待刮削',
                    'success': '已刮削',
                    'failed': '刮削失败'
                };
                return map[file.scrape_status] || file.scrape_status || '-';
            },

            getScrapeBadgeClass(file) {
                const batchItem = this.getScrapeBatchItem(file);
                if (batchItem) {
                    return this.getScrapeBatchBadgeClass(batchItem.status);
                }

                const map = {
                    'pending': 'pending',
                    'success': 'processed',
                    'failed': 'failed'
                };
                return map[file.scrape_status] || 'pending';
            },

            canSelectScrapeFile(file) {
                return this.view === 'scrape' &&
                    file.scrape_status === 'pending' &&
                    !this.isScrapeBatchItemBlocking(file);
            },

            getScrapeStatusActions(file) {
                const batchItem = this.getScrapeBatchItem(file);
                if (batchItem) {
                    if (batchItem.status === 'failed') {
                        return [
                            { key: 'scrape', label: '刮削', icon: 'sparkles' }
                        ];
                    }
                    return [];
                }

                if (file.scrape_status === 'pending' || file.scrape_status === 'failed') {
                    return [
                        { key: 'scrape', label: '刮削', icon: 'sparkles' }
                    ];
                }
                return [];
            },

            hasScrapeStatusAction(file) {
                if (this.isScrapeBatchItemBlocking(file)) {
                    return false;
                }
                return this.view === 'scrape' && this.getScrapeStatusActions(file).length > 0;
            },

            getScrapeFilterLabel(filter) {
                const map = {
                    all: '全部',
                    pending: '已整理',
                    success: '已刮削',
                    failed: '刮削失败'
                };
                return map[filter] || filter;
            },

            getScrapeSourceLabel(source) {
                const map = {
                    javdb: 'JavDB',
                    javtrailers: 'JavTrailers'
                };
                return map[source] || source || '-';
            },

            getScrapeStageLabel(stage, source) {
                const sourceLabel = this.getScrapeSourceLabel(source);

                if (stage === 'querying_source') {
                    return `正在查询 ${sourceLabel}`;
                }
                if (stage === 'fetching_detail') {
                    return `${sourceLabel} 已返回结果，正在读取详情页`;
                }

                const map = {
                    queued: '已加入刮削队列',
                    validating: '正在检查文件信息',
                    parsing_metadata: '详情页读取成功，正在解析元数据',
                    writing_nfo: '元数据解析成功，正在生成 NFO 文件',
                    downloading_poster: 'NFO 已生成，正在下载封面图片',
                    finalizing: '正在保存刮削结果',
                    success: '刮削完成',
                    failed: '刮削失败'
                };
                return map[stage] || stage || '-';
            },

            getScrapeErrorUserMessage(file) {
                return file?.scrape_error_user_message || '刮削过程中发生未知错误';
            },

            isBatchItemBlocking(file) {
                const batchItem = this.getBatchItem(file);
                if (!batchItem) {
                    return false;
                }
                return this.batchRunning || batchItem.status === 'processing';
            },

            isScrapeBatchItemBlocking(file) {
                const batchItem = this.getScrapeBatchItem(file);
                if (!batchItem) {
                    return false;
                }
                return this.scrapeBatchRunning || batchItem.status === 'processing';
            },

            hasStatusAction(file) {
                if (this.isBatchItemBlocking(file)) {
                    return false;
                }
                return this.view === 'scan' && this.getStatusActions(file).length > 0;
            },

            getStatusActionClass(file) {
                return `status-${this.getBadgeClass(file)}`;
            },

            getStatusRailStyle(file) {
                const actionCount = this.getStatusActions(file).length;
                const collapsedWidth = 100;
                const slotWidth = 34;
                const gap = 6;
                const actionsPadding = actionCount > 0 ? 12 : 0;
                const expandedWidth = collapsedWidth + actionsPadding + (actionCount * slotWidth) + (Math.max(actionCount - 1, 0) * gap);
                return `--status-width-collapsed: ${collapsedWidth}px; --status-width-expanded: ${expandedWidth}px;`;
            },

            getScrapeStatusRailStyle(file) {
                const actionCount = this.getScrapeStatusActions(file).length;
                const collapsedWidth = 100;
                const slotWidth = 34;
                const gap = 6;
                const actionsPadding = actionCount > 0 ? 12 : 0;
                const expandedWidth = collapsedWidth + actionsPadding + (actionCount * slotWidth) + (Math.max(actionCount - 1, 0) * gap);
                return `--status-width-collapsed: ${collapsedWidth}px; --status-width-expanded: ${expandedWidth}px;`;
            },

            canSelectFile(file) {
                return this.view === 'scan' &&
                    file.status === 'pending' &&
                    !this.isBatchItemBlocking(file);
            },

            getSelectionDisabledReason(file) {
                if (this.isBatchItemBlocking(file)) {
                    return '该文件已在当前批处理中';
                }
                if (file.status === 'duplicate') {
                    return '重复项不能批量勾选，请使用右侧按钮单独整理';
                }
                if (this.canSelectFile(file)) {
                    return '';
                }
                return '仅待整理项可加入整理集合';
            },

            getStatusSortWeight(file) {
                const status = file.identified_code ? (file.status || 'pending') : 'skipped';
                const order = {
                    pending: 0,
                    duplicate: 1,
                    target_exists: 2,
                    skipped: 3,
                    processed: 4,
                    failed: 5
                };
                return order[status] ?? 9;
            },

            getSortFieldIcon(field) {
                const iconMap = {
                    default: 'sort_default',
                    time: 'clock',
                    code: 'hashtag',
                    status: 'circle_status'
                };
                return this.getUiIcon(iconMap[field] || 'sort_default');
            },

            compareNatural(left, right) {
                return this.collator.compare(left || '', right || '');
            },

            compareCodeSort(a, b, direction = 1) {
                const aCode = a.identified_code;
                const bCode = b.identified_code;

                if (aCode && bCode) {
                    return this.compareNatural(aCode, bCode) * direction;
                }
                if (aCode && !bCode) {
                    return -1;
                }
                if (!aCode && bCode) {
                    return 1;
                }

                return this.compareNatural(this.getFilename(a.original_path), this.getFilename(b.original_path)) * direction;
            },

            compareTimeSort(a, b, direction = this.sortDirection) {
                const multiplier = direction === 'asc' ? 1 : -1;
                const aTime = Date.parse(a.updated_at || '') || 0;
                const bTime = Date.parse(b.updated_at || '') || 0;
                const diff = (aTime - bTime) * multiplier;
                if (diff !== 0) {
                    return diff;
                }
                return this.compareCodeSort(a, b, 1);
            },

            compareStatusSort(a, b, direction = this.sortDirection) {
                const multiplier = direction === 'asc' ? 1 : -1;
                const diff = (this.getStatusSortWeight(a) - this.getStatusSortWeight(b)) * multiplier;
                if (diff !== 0) {
                    return diff;
                }
                return this.compareCodeSort(a, b, 1);
            },

            compareDefaultSort(a, b) {
                if (a.identified_code && b.identified_code) {
                    const codeDiff = this.compareNatural(a.identified_code, b.identified_code);
                    if (codeDiff !== 0) {
                        return codeDiff;
                    }

                    const statusDiff = this.getStatusSortWeight(a) - this.getStatusSortWeight(b);
                    if (statusDiff !== 0) {
                        return statusDiff;
                    }

                    const filenameDiff = this.compareNatural(this.getFilename(a.original_path), this.getFilename(b.original_path));
                    if (filenameDiff !== 0) {
                        return filenameDiff;
                    }

                    return this.compareNatural(a.original_path, b.original_path);
                }
                if (a.identified_code && !b.identified_code) {
                    return -1;
                }
                if (!a.identified_code && b.identified_code) {
                    return 1;
                }

                const statusDiff = this.getStatusSortWeight(a) - this.getStatusSortWeight(b);
                if (statusDiff !== 0) {
                    return statusDiff;
                }

                return this.compareNatural(this.getFilename(a.original_path), this.getFilename(b.original_path));
            },

            compareSort(a, b) {
                if (this.view === 'scan' && this.sortField === 'default') {
                    return this.compareDefaultSort(a, b);
                }

                if (this.sortField === 'time') {
                    return this.compareTimeSort(a, b);
                }

                if (this.sortField === 'code') {
                    return this.compareCodeSort(a, b, this.sortDirection === 'asc' ? 1 : -1);
                }

                if (this.sortField === 'status') {
                    return this.compareStatusSort(a, b);
                }

                return this.compareDefaultSort(a, b);
            },

            updateRowGlow(event) {
                const row = event.currentTarget;
                const rect = row.getBoundingClientRect();
                row.style.setProperty('--x', `${event.clientX - rect.left}px`);
                row.style.setProperty('--y', `${event.clientY - rect.top}px`);
            },

            updateStatGlow(event) {
                const card = event.currentTarget;
                const rect = card.getBoundingClientRect();
                card.style.setProperty('--x', `${event.clientX - rect.left}px`);
                card.style.setProperty('--y', `${event.clientY - rect.top}px`);
            },

            getStatusActions(file) {
                if (['pending', 'duplicate'].includes(file.status)) {
                    return [
                        { key: 'organize', label: '整理文件', icon: 'organize' },
                        { key: 'delete', label: '删除文件', icon: 'delete' }
                    ];
                }

                if (['skipped', 'target_exists'].includes(file.status)) {
                    return [
                        { key: 'delete', label: '删除文件', icon: 'delete' }
                    ];
                }

                return [];
            },

            getBatchItem(file) {
                return this.batchItemsIndex[file.id] || null;
            },

            getScrapeBatchItem(file) {
                return this.scrapeBatchItemsIndex[file.id] || null;
            },

            getUiIcon(name) {
                const icons = {
                    scan: `
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                            <path d="M3 7.5A1.5 1.5 0 0 1 4.5 6h4l1.6 1.8H19.5A1.5 1.5 0 0 1 21 9.3v7.2A1.5 1.5 0 0 1 19.5 18h-15A1.5 1.5 0 0 1 3 16.5z"/>
                            <path d="M8.5 12h7"/>
                        </svg>
                    `,
                    organize: `
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                            <path d="M12 3.5l1.4 3.6L17 8.5l-3.6 1.4L12 13.5l-1.4-3.6L7 8.5l3.6-1.4z"/>
                            <path d="M18.5 13.5l.8 2 .2.5.5.2 2 .8-2 .8-.5.2-.2.5-.8 2-.8-2-.2-.5-.5-.2-2-.8 2-.8.5-.2.2-.5z"/>
                            <path d="M6 15.5l.9 2.2.2.4.4.2 2.2.9-2.2.9-.4.2-.2.4L6 23l-.9-2.2-.2-.4-.4-.2-2.2-.9 2.2-.9.4-.2.2-.4z"/>
                        </svg>
                    `,
                    sort_default: `
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                            <path d="M5 7h8"/>
                            <path d="M5 12h14"/>
                            <path d="M5 17h10"/>
                            <circle cx="16.5" cy="7" r="1.5"/>
                            <circle cx="9.5" cy="17" r="1.5"/>
                        </svg>
                    `,
                    sort_code_asc: `
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                            <path d="M7 18V6"/>
                            <path d="M4.5 8.5L7 6l2.5 2.5"/>
                            <path d="M13 17h4"/>
                            <path d="M13 13.5l1.8-2.5h2.2"/>
                            <path d="M13 8h4"/>
                        </svg>
                    `,
                    sort_code_desc: `
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                            <path d="M7 6v12"/>
                            <path d="M4.5 15.5L7 18l2.5-2.5"/>
                            <path d="M13 8h4"/>
                            <path d="M13 12.5l1.8 2.5h2.2"/>
                            <path d="M13 17h4"/>
                        </svg>
                    `,
                    clock: `
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                            <circle cx="12" cy="12" r="8"/>
                            <path d="M12 7.5v4.8l3 1.7"/>
                        </svg>
                    `,
                    hashtag: `
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                            <path d="M9 4L7 20"/>
                            <path d="M17 4l-2 16"/>
                            <path d="M4 9h16"/>
                            <path d="M3 15h16"/>
                        </svg>
                    `,
                    circle_status: `
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                            <circle cx="12" cy="12" r="8"/>
                            <circle cx="12" cy="12" r="2.2"/>
                        </svg>
                    `,
                    sort_asc: `
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                            <path d="M7 18V6"/>
                            <path d="M4.5 8.5L7 6l2.5 2.5"/>
                            <path d="M13 16h6"/>
                            <path d="M13 12h4.5"/>
                            <path d="M13 8h3"/>
                        </svg>
                    `,
                    sort_desc: `
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                            <path d="M7 6v12"/>
                            <path d="M4.5 15.5L7 18l2.5-2.5"/>
                            <path d="M13 8h6"/>
                            <path d="M13 12h4.5"/>
                            <path d="M13 16h3"/>
                        </svg>
                    `,
                    chevron_down: `
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                            <path d="M6.5 9.5L12 15l5.5-5.5"/>
                        </svg>
                    `,
                    delete: `
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                            <path d="M4 7h16"/>
                            <path d="M9 7V4.5h6V7"/>
                            <path d="M7.5 7l.7 11a1.5 1.5 0 0 0 1.5 1.4h4.6a1.5 1.5 0 0 0 1.5-1.4l.7-11"/>
                            <path d="M10 10.5v5.5"/>
                            <path d="M14 10.5v5.5"/>
                        </svg>
                    `,
                    cancel: `
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                            <path d="M6 6l12 12"/>
                            <path d="M18 6L6 18"/>
                        </svg>
                    `,
                    sparkles: `
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                            <path d="M12 2l1.1 3.4L16.5 7l-3.4 1.6L12 12l-1.1-3.4L7.5 7l3.4-1.6z"/>
                            <path d="M5 14l.6 1.8L7.5 17l-1.9.7L5 19.5l-.6-1.8L2.5 17l1.9-.7z"/>
                            <path d="M17 13l.7 2.2L20 16.5l-2.3.8L17 19.5l-.7-2.2L14.5 16.5l2.3-.8z"/>
                        </svg>
                    `,
                    file_search: `
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                            <polyline points="14 2 14 8 20 8"/>
                            <circle cx="12" cy="14" r="3"/>
                            <path d="m16.5 16.5-2.5-2.5"/>
                        </svg>
                    `

                };
                return icons[name] || '';
            },

            getFilterLabel(filter) {
                const map = {
                    all: '全部',
                    identified: '已识别',
                    unidentified: '未识别',
                    pending: '待整理',
                    duplicate: '重复',
                    target_exists: '已存在',
                    processed: '已整理'
                };
                return map[filter] || filter;
            },

            getResultLabel(result) {
                const match = this.scanFilesCache.find(file => file.id === result.file_id);
                return match?.identified_code || this.getFilename(result.original_path);
            },
        };
    }

    window.NoctraRender = {
        createRender
    };
})(window);
