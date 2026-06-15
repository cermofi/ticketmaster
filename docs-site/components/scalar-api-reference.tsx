'use client';

import { ApiReferenceReact } from '@scalar/api-reference-react';
import '@scalar/api-reference-react/style.css';

const OPENAPI_URL = '/api/openapi.json';

export function ScalarApiReference() {
  return (
    <div className="scalar-api-reference not-prose my-6 min-h-[70vh] w-full overflow-hidden rounded-lg border border-fd-border">
      <ApiReferenceReact
        configuration={{
          url: OPENAPI_URL,
        }}
      />
    </div>
  );
}
