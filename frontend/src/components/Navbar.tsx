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
  gap: 1.5rem;
  flex-wrap: wrap;
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

export default function Navbar() {
  const pathname = usePathname();
  const hardNavigate = (e: React.MouseEvent, href: string) => {
    e.preventDefault();
    window.location.href = href; // tving full reload
  };

  return (
    <Nav>
      <NavContainer>
        <NavLinks>
          <NavLink href="/" prefetch={false} onClick={(e) => hardNavigate(e, '/') } $active={pathname === '/'}>
            Aktiviteter
          </NavLink>
          <NavLink href="/statistikk" prefetch={false} onClick={(e) => hardNavigate(e, '/statistikk') } $active={pathname === '/statistikk'}>
            Statistikk
          </NavLink>
          <NavLink href="/ukesanalyse" prefetch={false} onClick={(e) => hardNavigate(e, '/ukesanalyse') } $active={pathname === '/ukesanalyse'}>
            Løpsøkonomi
          </NavLink>
          <NavLink href="/hrv" prefetch={false} onClick={(e) => hardNavigate(e, '/hrv') } $active={pathname === '/hrv'}>
            HRV
          </NavLink>
          <NavLink href="/vo2max" prefetch={false} onClick={(e) => hardNavigate(e, '/vo2max') } $active={pathname === '/vo2max'}>
            VO2Max
          </NavLink>
          <NavLink href="/stress" prefetch={false} onClick={(e) => hardNavigate(e, '/stress') } $active={pathname === '/stress'}>
            Stress
          </NavLink>
          <NavLink href="/daglig-readiness" prefetch={false} onClick={(e) => hardNavigate(e, '/daglig-readiness') } $active={pathname === '/daglig-readiness'}>
            Daglig Readiness
          </NavLink>
          <NavLink href="/body-battery" prefetch={false} onClick={(e) => hardNavigate(e, '/body-battery') } $active={pathname === '/body-battery'}>
            Body Battery
          </NavLink>
          <NavLink href="/sovn" prefetch={false} onClick={(e) => hardNavigate(e, '/sovn') } $active={pathname === '/sovn'}>
            Søvn
          </NavLink>
          <NavLink href="/training-status" prefetch={false} onClick={(e) => hardNavigate(e, '/training-status') } $active={pathname === '/training-status'}>
            Treningstatus
          </NavLink>
          <NavLink href="/training-stress" prefetch={false} onClick={(e) => hardNavigate(e, '/training-stress') } $active={pathname === '/training-stress'}>
            Training Stress Score
          </NavLink>
          <NavLink href="/synkronisering" prefetch={false} onClick={(e) => hardNavigate(e, '/synkronisering') } $active={pathname === '/synkronisering'}>
            Synkronisering
          </NavLink>
        </NavLinks>
      </NavContainer>
    </Nav>
  );
} 