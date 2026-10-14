import Icon from '../Icon';

/**
 * A question mark you can open, for the numbers that are meaningless alone.
 *
 * "RICE 114,953", "Weighted 75.3" and "Effort 2" are honest labels for scores
 * that only mean something next to the scale that produced them. Rather than
 * caption every screen with a legend, the explainer sits on the label itself.
 * Built on <details> so it opens by keyboard and is announced by assistive
 * tech without a focus trap or any state of its own.
 */
export default function Hint({ label = 'What this means', align = 'left', side = 'bottom', children }) {
  return (
    <details className={`hint is-${side} is-${align}`}>
      <summary aria-label={label} title={label}>
        <Icon name="info" size={12} />
      </summary>
      <div className="hint-pop" role="note">
        {children}
      </div>
    </details>
  );
}
