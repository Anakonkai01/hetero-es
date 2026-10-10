import { Link } from "react-router";

export function NotFoundPage() {
  return (
    <div className="card">
      <div className="empty">
        <b>Page not found</b>
        <span>The page you are looking for does not exist.</span>
        <Link className="btn pri" to="/dashboard">
          Back to Dashboard
        </Link>
      </div>
    </div>
  );
}
