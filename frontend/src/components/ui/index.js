/**
 * The UI kit.
 *
 * Pages import from here and never invent their own markup for these concepts.
 * If a screen needs a new visual idea, it belongs in this folder — not inline
 * in a page.
 */

export { default as Button, IconButton } from './Button';
export { Card, CardHeader, CardBody, CardFooter, Stat, StatGrid } from './Card';
export { PageHeader, Section, Toolbar, ToolbarField } from './Layout';
export { default as ProgressTrail } from './ProgressTrail';
export { Field, Input, Textarea, Select, SearchInput, Segmented } from './Controls';
export { default as Menu } from './Menu';
export { default as Hint } from './Hint';
export { default as WorkspaceSwitcher } from './WorkspaceSwitcher';
export { Tabs } from './Tabs';
export { default as Modal } from './Modal';
export {
  Badge,
  Pill,
  Alert,
  EmptyState,
  ErrorState,
  Spinner,
  ProgressBar,
  LoadingState,
} from './Feedback';
export {
  Skeleton,
  SkeletonText,
  SkeletonStat,
  SkeletonStatGrid,
  SkeletonCard,
  SkeletonCardGrid,
  SkeletonTable,
  SkeletonChart,
  SkeletonList,
  SkeletonBoard,
  SkeletonPage,
} from './Skeleton';
