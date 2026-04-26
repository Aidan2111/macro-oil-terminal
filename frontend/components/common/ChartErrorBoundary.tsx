"use client";

import * as React from "react";
import { ErrorState } from "./ErrorState";

type Props = {
  /** Friendly chart name, e.g. "Brent–WTI spread chart". */
  label: string;
  children: React.ReactNode;
};

type State = {
  err: Error | null;
};

/**
 * Hand-rolled ErrorBoundary scoped to a single chart. Recharts is
 * happy to throw on degenerate data shapes (NaN domain, empty series
 * after filtering) and an unguarded throw kills the whole route. This
 * boundary keeps every other chart on the page alive and renders the
 * existing red ErrorState card in place of the busted one.
 *
 * We avoid pulling in `react-error-boundary` to keep the dependency
 * surface tight — class component is ~20 lines and covers the case.
 */
export class ChartErrorBoundary extends React.Component<Props, State> {
  state: State = { err: null };

  static getDerivedStateFromError(err: Error): State {
    return { err };
  }

  componentDidCatch(err: Error, info: React.ErrorInfo): void {
    // eslint-disable-next-line no-console
    console.error(`[chart:${this.props.label}]`, err, info.componentStack);
  }

  reset = () => {
    this.setState({ err: null });
  };

  render() {
    if (this.state.err) {
      return (
        <div role="alert" aria-label={`${this.props.label} failed to render`}>
          <ErrorState
            message={`${this.props.label} failed to render: ${
              this.state.err.message || "unknown error"
            }`}
            retry={this.reset}
          />
        </div>
      );
    }
    return this.props.children;
  }
}
