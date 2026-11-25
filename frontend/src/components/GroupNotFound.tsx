import { Link } from 'react-router-dom';
import { useT } from '../i18n';

export function GroupNotFound() {
  const t = useT();
  return (
    <div className="notice" role="alert">
      <p className="mt-0">{t.app.groupNotFound}</p>
      <Link to="/" className="button small">{t.app.toStart}</Link>
    </div>
  );
}
