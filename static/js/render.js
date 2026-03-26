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
                    'pending': '待处理',
                    'target_exists': '已存在',
                    'processed': '已处理',
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

            getBatchItemStatusText(status) {
                const map = {
                    pending: '待处理',
                    processing: '处理中',
                    success: '已完成',
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

            hasStatusAction(file) {
                if (this.getBatchItem(file)) {
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

            canSelectFile(file) {
                return this.view === 'scan' && file.status === 'pending' && !this.getBatchItem(file);
            },

            getSelectionDisabledReason(file) {
                if (this.getBatchItem(file)) {
                    return '该文件已在当前批处理中';
                }
                if (this.canSelectFile(file)) {
                    return '';
                }
                return '仅待处理项可加入整理集合';
            },

            getStatusSortWeight(file) {
                const status = file.identified_code ? (file.status || 'pending') : 'skipped';
                const order = {
                    pending: 0,
                    target_exists: 1,
                    skipped: 2,
                    processed: 3,
                    failed: 4
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
                if (this.view === 'history') {
                    return this.compareTimeSort(a, b, 'desc');
                }
                return this.compareCodeSort(a, b, 1);
            },

            compareDefaultSort(a, b) {
                const statusDiff = this.getStatusSortWeight(a) - this.getStatusSortWeight(b);
                if (statusDiff !== 0) {
                    return statusDiff;
                }

                if (a.identified_code && b.identified_code) {
                    return this.compareNatural(a.identified_code, b.identified_code);
                }
                if (a.identified_code && !b.identified_code) {
                    return -1;
                }
                if (!a.identified_code && b.identified_code) {
                    return 1;
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
                if (file.status === 'pending') {
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
                    `
                };
                return icons[name] || '';
            },

            getFilterLabel(filter) {
                const map = {
                    all: '全部',
                    identified: '已识别',
                    unidentified: '未识别',
                    pending: '待处理',
                    target_exists: '已存在',
                    processed: '已处理'
                };
                return map[filter] || filter;
            },

            getResultLabel(result) {
                const match = this.scanFilesCache.find(file => file.id === result.file_id)
                    || this.historyFilesCache.find(file => file.id === result.file_id);
                return match?.identified_code || this.getFilename(result.original_path);
            },
        };
    }

    window.NoctraRender = {
        createRender
    };
})(window);
