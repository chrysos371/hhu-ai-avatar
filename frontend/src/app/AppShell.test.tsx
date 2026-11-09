import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppShell } from './AppShell';
it('renders accessible navigation, local warning and no invented metrics',()=>{
  render(<MemoryRouter><AppShell/></MemoryRouter>);
  for(const name of ['总览','对话观测','人设管理','情绪干预','记忆中枢','知识与学习','提醒','工具','操作审计']) expect(screen.getByRole('link',{name})).toBeInTheDocument();
  expect(screen.getByRole('link',{name:'总览'})).toHaveAttribute('aria-current','page');
  expect(screen.getByText(/单用户.*本机/)).toBeInTheDocument();
  expect(screen.queryByText('99.9%')).not.toBeInTheDocument();
});
