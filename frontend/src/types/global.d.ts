/**
 * window.Helploom is set by public/widget.js (widget/src/index.ts) once the widget
 * has mounted; the dashboard's test page uses it to unmount the widget again.
 */
interface HelploomWidgetApi {
  open: () => void;
  close: () => void;
  destroy: () => void;
}

interface Window {
  Helploom?: HelploomWidgetApi;
}
