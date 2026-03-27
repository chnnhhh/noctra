(function (window) {
    function createUtils() {
        return {
            getFilename(path) {
                if (!path) return '-';
                return path.split('/').pop();
            },

            fallbackCopyToClipboard(text) {
                const textarea = document.createElement('textarea');
                textarea.value = text;
                textarea.setAttribute('readonly', '');
                textarea.style.position = 'fixed';
                textarea.style.opacity = '0';
                textarea.style.pointerEvents = 'none';
                document.body.appendChild(textarea);
                textarea.select();
                const copied = document.execCommand('copy');
                document.body.removeChild(textarea);

                if (!copied) {
                    throw new Error('当前浏览器不支持复制');
                }
            },

            getCopyToastAnchor(event) {
                if (!event) {
                    return null;
                }

                const target = event.currentTarget;
                const viewportWidth = window.innerWidth;
                const viewportHeight = window.innerHeight;
                const fallbackRect = target?.getBoundingClientRect?.();
                const cursorX = typeof event.clientX === 'number'
                    ? event.clientX
                    : (fallbackRect ? fallbackRect.left + fallbackRect.width / 2 : viewportWidth / 2);
                const cursorY = typeof event.clientY === 'number'
                    ? event.clientY
                    : (fallbackRect ? fallbackRect.top + fallbackRect.height / 2 : viewportHeight / 2);

                let placement = 'right';
                let x = cursorX;
                if (cursorX > viewportWidth - 240) {
                    placement = 'left';
                    x = cursorX;
                }

                const y = Math.max(24, Math.min(viewportHeight - 24, cursorY - 2));

                return { x, y, placement };
            },

            showCopyToast(anchor, message = '路径已复制到剪贴板') {
                if (!anchor) {
                    this.success = message;
                    setTimeout(() => {
                        this.success = null;
                    }, 1600);
                    return;
                }

                if (this.copyToastTimer) {
                    clearTimeout(this.copyToastTimer);
                }

                this.success = null;
                this.copyToast.visible = false;
                this.copyToast.text = message;
                this.copyToast.x = anchor.x;
                this.copyToast.y = anchor.y;
                this.copyToast.placement = anchor.placement;

                requestAnimationFrame(() => {
                    this.copyToast.visible = true;
                });

                this.copyToastTimer = setTimeout(() => {
                    this.copyToast.visible = false;
                    this.copyToastTimer = null;
                }, 1200);
            },

            async copyToClipboard(text, event = null, message = '路径已复制到剪贴板') {
                const anchor = this.getCopyToastAnchor(event);
                try {
                    if (navigator.clipboard && window.isSecureContext) {
                        await navigator.clipboard.writeText(text);
                    } else {
                        this.fallbackCopyToClipboard(text);
                    }
                    this.error = null;
                    this.showCopyToast(anchor, message);
                } catch (err) {
                    this.error = '复制失败：' + err.message;
                }
            },

            formatProcessedDate(value) {
                if (!value) {
                    return '--';
                }

                const date = new Date(value);
                if (Number.isNaN(date.getTime())) {
                    return '--';
                }

                const year = date.getFullYear();
                const month = String(date.getMonth() + 1).padStart(2, '0');
                const day = String(date.getDate()).padStart(2, '0');
                return `${year}-${month}-${day}`;
            },

            formatProcessedTime(value) {
                if (!value) {
                    return '--';
                }

                const date = new Date(value);
                if (Number.isNaN(date.getTime())) {
                    return '--';
                }

                const hours = String(date.getHours()).padStart(2, '0');
                const minutes = String(date.getMinutes()).padStart(2, '0');
                return `${hours}:${minutes}`;
            },

            formatOrganizeFailures(results) {
                const failedResults = results.filter(result => result.status === 'failed');
                if (failedResults.length === 0) {
                    return null;
                }

                const details = failedResults.slice(0, 3).map(result => {
                    const label = this.getResultLabel(result);
                    const reason = result.reason || '未知原因';
                    return `${label}：${reason}`;
                });
                const suffix = failedResults.length > 3 ? ' 等' : '';
                return `${failedResults.length} 个文件整理失败：${details.join('；')}${suffix}`;
            },
        };
    }

    window.NoctraUtils = {
        createUtils
    };
})(window);
