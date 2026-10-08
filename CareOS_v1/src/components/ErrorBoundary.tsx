import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { children: ReactNode };
type State = { failed: boolean };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("CareOS UI error", error, info.componentStack);
  }

  render() {
    if (this.state.failed) {
      return <main className="app-error-screen" role="alert"><h1>Something went wrong</h1><p>Reload the workspace to continue.</p><button className="primary-btn" onClick={() => window.location.reload()}>Reload</button></main>;
    }
    return this.props.children;
  }
}