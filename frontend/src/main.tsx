import React from 'react';
import ReactDOM from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import { registerSW } from 'virtual:pwa-register';
import { router } from './app/router';
import { queryClient } from './app/query-client';
import { Language } from './i18n/Language';
import { FeedbackProvider } from './components/Feedback';
import './index.css';

// New versions are installed in the background; the app offers a reload instead of switching mid-entry
const updateServiceWorker = registerSW({
  onNeedRefresh: () => window.dispatchEvent(new Event('carshare:update-available')),
});
window.addEventListener('carshare:apply-update', () => void updateServiceWorker(true));

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <Language>
        <FeedbackProvider>
          <RouterProvider router={router} />
        </FeedbackProvider>
      </Language>
    </QueryClientProvider>
  </React.StrictMode>,
);
