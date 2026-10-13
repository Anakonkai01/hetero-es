// Start-up, Quit and tray behaviour of the Worker main process, kept apart from Electron so it can be tested.
const MESSAGES = {
    SETUP_IN_PROGRESS: 'The runtime is still installing or being checked. Wait for it to finish, then quit. / Môi trường đang được cài hoặc kiểm tra. Hãy chờ xong rồi thoát.',
    DRAIN_NOT_CONFIRMED: 'Worker processes have not confirmed they stopped, so the app stays open. / Các tiến trình chưa xác nhận đã dừng nên ứng dụng vẫn mở.',
    ACTION_IN_PROGRESS: 'Another action is still running. Try again in a moment. / Một thao tác khác đang chạy. Hãy thử lại sau giây lát.',
    AGENT_TIMEOUT: 'The local agent did not answer in time. / Tiến trình agent trên máy không phản hồi kịp.',
    AGENT_UNAVAILABLE: 'The local agent is not available. / Không dùng được agent trên máy.',
    SECURE_STORAGE_REQUIRED: 'Secure credential storage is unavailable on this computer. / Máy này không có kho lưu thông tin đăng nhập an toàn.',
    ACTION_FAILED: 'The action failed. Export diagnostics from the app. / Thao tác thất bại. Hãy xuất thông tin chẩn đoán trong ứng dụng.',
};
// A message safe to show: the code is kept for support, but free text (which could hold secrets) never is.
function describeCode(value) {
    const code = /^[A-Z][A-Z0-9_]+$/.test(value ?? '') ? value : 'ACTION_FAILED';
    return `${MESSAGES[code] ?? 'Something went wrong. / Đã xảy ra lỗi.'} (${code})`;
}
const codeOf = error => /^[A-Z][A-Z0-9_]+$/.test(error?.message ?? '') ? error.message : 'ACTION_FAILED';

class Lifecycle {
    constructor({ service, quitApp, show, notify, fail, log }) {
        Object.assign(this, { service, quitApp, show, notify, fail, log });
        this.exiting = false; this.busy = false; this.quitting = null;
    }
    // The gate for ordinary actions (connect, sign in, pair, ...). Quit and status never go through it.
    async run(action, work) {
        if (this.busy || this.quitting) throw Error('ACTION_IN_PROGRESS');
        this.busy = true;
        try { return await work(); } finally { this.busy = false; }
    }
    // Stop everything and leave. Never refused because another action is running: the service cancels waiting
    // network reads, and the app only exits once the owned processes are confirmed stopped.
    quit() {
        if (this.exiting) return Promise.resolve({ drained: true });
        this.quitting ??= (async () => {
            try {
                const state = await this.service.quit();
                if (!state.drained) { this.show(); return state; }
                this.exiting = true; this.quitApp();
                return state;
            } finally { this.quitting = null; }
        })();
        return this.quitting;
    }
    // Quit from the tray or the system: the user is not looking at the window, so every failure is announced.
    async userQuit() {
        try {
            const state = await this.quit();
            if (!state.drained) this.notify('HeteroES Worker', describeCode('DRAIN_NOT_CONFIRMED'));
        } catch (error) {
            this.log.error('quit failed', error); this.show();
            this.notify('HeteroES Worker', describeCode(codeOf(error)));
        }
    }
    async stopSafely() {
        const running = !!this.service.bridge;
        try {
            await this.service.contribution(false);
            this.notify('HeteroES Worker', running ? 'Contribution is OFF. / Đóng góp GPU đang tắt.' : 'Nothing is running. / Không có gì đang chạy.');
        } catch (error) {
            this.log.error('stop failed', error);
            this.notify('HeteroES Worker', describeCode(codeOf(error)));
        }
    }
    async startupFailed(error) {
        this.log.error('startup failed', error);
        this.exiting = true;
        this.fail('HeteroES Worker could not start / không khởi động được', describeCode(codeOf(error)));
        this.quitApp();
    }
}
module.exports = { Lifecycle, describeCode, codeOf };
