'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import styled from 'styled-components';

const Nav = styled.nav`
  background: #2c3e50;
  padding: 0.25rem 0.5rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
`;

const NavContainer = styled.div`
  display: flex;
  justify-content: flex-start;
  align-items: center;
  padding-left: 0.75rem;
`;

const NavLinks = styled.div`
  display: flex;
  gap: 1rem;
  flex-wrap: nowrap;
  overflow-x: auto;
  
  &::-webkit-scrollbar {
    height: 4px;
  }
  
  &::-webkit-scrollbar-track {
    background: rgba(255, 255, 255, 0.1);
  }
  
  &::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.3);
    border-radius: 2px;
  }
`;

const NavLink = styled(Link)<{ $active?: boolean }>`
  color: ${props => props.$active ? '#3498db' : 'white'};
  text-decoration: none;
  font-weight: ${props => props.$active ? 'bold' : 'normal'};
  padding: 0.25rem 0.75rem;
  border-radius: 4px;
  transition: all 0.2s ease;

  &:hover {
    background: rgba(255, 255, 255, 0.1);
  }
`;

/** @deprecated Legacy navbar — AppShell is primary. Kept for legacy pages without reload hacks. */
export default function Navbar() {
  const pathname = usePathname();

  return (
    <Nav aria-label="Legacy navigasjon">
      <NavContainer>
        <NavLinks>
          <NavLink href="/aktiviteter" prefetch $active={pathname?.startsWith('/aktiviteter') || pathname?.startsWith('/activities')}>
            Aktiviteter
          </NavLink>
          <NavLink href="/analyse" prefetch $active={pathname?.startsWith('/analyse')}>
            Analyse
          </NavLink>
          <NavLink href="/statistikk" prefetch $active={pathname === '/statistikk'}>
            Statistikk
          </NavLink>
          <NavLink href="/sammenhenger" prefetch $active={pathname === '/sammenhenger'}>
            Sammenhenger
          </NavLink>
          <NavLink href="/ukesanalyse" prefetch $active={pathname === '/ukesanalyse'}>
            Løpsøkonomi
          </NavLink>
          <NavLink href="/analytics" prefetch $active={pathname === '/analytics'}>
            Løpeanalyse
          </NavLink>
          <NavLink href="/hrv" prefetch $active={pathname === '/hrv'}>
            HRV
          </NavLink>
          <NavLink href="/vo2max" prefetch $active={pathname === '/vo2max'}>
            VO2Max
          </NavLink>
          <NavLink href="/stress" prefetch $active={pathname === '/stress'}>
            Stress
          </NavLink>
          <NavLink href="/daglig-readiness" prefetch $active={pathname === '/daglig-readiness'}>
            Daglig Readiness
          </NavLink>
          <NavLink href="/body-battery" prefetch $active={pathname === '/body-battery'}>
            Body Battery
          </NavLink>
          <NavLink href="/sovn" prefetch $active={pathname === '/sovn'}>
            Søvn
          </NavLink>
          <NavLink href="/training-status" prefetch $active={pathname === '/training-status'}>
            Treningstatus
          </NavLink>
          <NavLink href="/training-stress" prefetch $active={pathname === '/training-stress'}>
            Training Stress
          </NavLink>
          <NavLink href="/synkronisering" prefetch $active={pathname === '/synkronisering'}>
            Synkronisering
          </NavLink>
        </NavLinks>
      </NavContainer>
    </Nav>
  );
}
