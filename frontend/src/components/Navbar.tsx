'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import styled from 'styled-components';

const Nav = styled.nav`
  background: #2c3e50;
  padding: 0.5rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
`;

const NavContainer = styled.div`
  display: flex;
  justify-content: flex-start;
  align-items: center;
  gap: 4rem;
  padding-left: 1rem;
`;

const Logo = styled.span`
  color: white;
  font-size: 2rem;
  font-weight: bold;
  line-height: 1;
  display: flex;
  align-items: center;
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
          <NavLink href="/hrv" $active={pathname === '/hrv'}>
            HRV
          </NavLink>
          <NavLink href="/daglig-readiness" $active={pathname === '/daglig-readiness'}>
            Daglig Readiness
          </NavLink>
          <NavLink href="/body-battery" $active={pathname === '/body-battery'}>
            Body Battery
          </NavLink>
          <NavLink href="/training-stress" $active={pathname === '/training-stress'}>
            Training Stress Score
          </NavLink>
        </NavLinks>
      </NavContainer>
    </Nav>
  );
} 