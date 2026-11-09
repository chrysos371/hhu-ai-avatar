import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router-dom';
import { createRouter } from './router';
const client=new QueryClient({defaultOptions:{queries:{retry:1,staleTime:10000}}});
const router=createRouter();
export function App(){return <QueryClientProvider client={client}><RouterProvider router={router}/></QueryClientProvider>;}
