'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import styled from 'styled-components';

const Nav = styled.nav`
  background: #2c3e50;
  padding: 1rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
`;

const NavContainer = styled.div`
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
`;

const Logo = styled.span`
  color: white;
  font-size: 1.5rem;
  font-weight: bold;
`;

const NavLinks = styled.div`
  display: flex;
  gap: 2rem;
`;

const NavLink = styled(Link)<{ $active?: boolean }>`
  color: ${props => props.$active ? '#3498db' : 'white'};
  text-decoration: none;
  font-weight: ${props => props.$active ? 'bold' : 'normal'};
  padding: 0.5rem 1rem;
  border-radius: 4px;
  transition: all 0.2s ease;

  &:hover {
    background: rgba(255, 255, 255, 0.1);
  }
`;

export default function Navbar() {
  const pathname = usePathname();

  return (
    <Nav>
      <NavContainer>
        <Logo>TreningsApp</Logo>
        <NavLinks>
          <NavLink href="/" $active={pathname === '/'}>
            Aktiviteter
          </NavLink>
          <NavLink href="/statistikk" $active={pathname === '/statistikk'}>
            Statistikk
          </NavLink>
          <NavLink href="/ukesanalyse" $active={pathname === '/ukesanalyse'}>
            Løpsøkonomi
          </NavLink>
          <NavLink href="/sovn" $active={pathname === '/sovn'}>
            Søvn
          </NavLink>
          <NavLink href="/grafer" $active={pathname === '/grafer'}>
            Grafer
          </NavLink>
        </NavLinks>
      </NavContainer>
    </Nav>
  );
} 