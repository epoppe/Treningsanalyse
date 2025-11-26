'use client';

import styled, { keyframes } from 'styled-components';
import { memo } from 'react';

const shimmer = keyframes`
  0% {
    background-position: -468px 0;
  }
  100% {
    background-position: 468px 0;
  }
`;

const SkeletonBase = styled.div`
  animation: ${shimmer} 1.2s ease-in-out infinite;
  background: linear-gradient(
    to right,
    #f0f0f0 0%,
    #e0e0e0 20%,
    #f0f0f0 40%,
    #f0f0f0 100%
  );
  background-size: 936px 100%;
  border-radius: 4px;
`;

const SkeletonCard = styled(SkeletonBase)`
  width: 100%;
  height: 120px;
  margin-bottom: 1rem;
  border-radius: 8px;
`;

const SkeletonText = styled(SkeletonBase)<{ width?: string; height?: string }>`
  width: ${props => props.width || '100%'};
  height: ${props => props.height || '16px'};
  margin-bottom: 0.5rem;
`;

const SkeletonChart = styled(SkeletonBase)`
  width: 100%;
  height: 400px;
  border-radius: 8px;
  margin-bottom: 1rem;
`;

const Container = styled.div`
  padding: 1rem;
`;

interface SkeletonLoaderProps {
  type?: 'card' | 'text' | 'chart' | 'list';
  count?: number;
}

const SkeletonLoader = ({ type = 'card', count = 3 }: SkeletonLoaderProps) => {
  if (type === 'chart') {
    return <SkeletonChart />;
  }

  if (type === 'text') {
    return (
      <Container>
        <SkeletonText width="60%" height="24px" />
        <SkeletonText width="80%" />
        <SkeletonText width="70%" />
      </Container>
    );
  }

  if (type === 'list') {
    return (
      <Container>
        {Array.from({ length: count }).map((_, index) => (
          <SkeletonCard key={index} />
        ))}
      </Container>
    );
  }

  // Default: card
  return (
    <Container>
      {Array.from({ length: count }).map((_, index) => (
        <SkeletonCard key={index} />
      ))}
    </Container>
  );
};

export default memo(SkeletonLoader);

















