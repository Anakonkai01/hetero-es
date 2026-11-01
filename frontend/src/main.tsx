import { ProductProvider } from '@heteroes/product-ui';
import '@heteroes/product-ui/theme.css';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router';
import { AppProviders } from './app/providers';
import { AppRouter } from './app/router';
import { loadRuntimeConfig } from './app/runtimeConfig';
import { initializeIdentity } from './app/identity';
import './index.css';
import './product.css';
async function start() {
  const config = await loadRuntimeConfig(import.meta.env.BASE_URL);
  if (!(await initializeIdentity(config))) return;
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <ProductProvider>
        <AppProviders>
          <BrowserRouter basename={config.basePath}>
            <AppRouter />
          </BrowserRouter>
        </AppProviders>
      </ProductProvider>
    </StrictMode>,
  );
}
void start().catch(() => {
  document.getElementById('root')!.textContent =
    'Sign-in is unavailable. Please reload. / Không thể đăng nhập. Vui lòng tải lại.';
});
