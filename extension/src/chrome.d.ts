// Minimal Chrome declarations keep the extension dependency-free.
declare namespace chrome {
  namespace sidePanel {
    function setPanelBehavior(options: { openPanelOnActionClick: boolean }): Promise<void>;
  }
  namespace runtime {
    const onInstalled: { addListener(callback: () => void): void };
  }
  namespace tabs {
    function create(options: { url: string; active?: boolean }): Promise<unknown>;
  }
}
