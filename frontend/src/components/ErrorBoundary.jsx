import { Component } from 'react'

class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  render() {
    if (!this.state.hasError) {
      return this.props.children
    }

    return (
      <main className="error-boundary-fallback">
        <h1>{this.props.title || 'Something went wrong'}</h1>
        <p>{this.props.message || 'An unexpected error occurred. Please reload the page.'}</p>
        <button type="button" onClick={() => window.location.reload()}>
          {this.props.reloadLabel || 'Reload'}
        </button>
      </main>
    )
  }
}

export default ErrorBoundary
