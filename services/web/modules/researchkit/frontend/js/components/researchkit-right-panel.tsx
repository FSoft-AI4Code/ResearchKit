import { FC } from 'react'
import { Panel } from 'react-resizable-panels'
import classNames from 'classnames'
import { HorizontalResizeHandle } from '@/features/ide-react/components/resize/horizontal-resize-handle'
import { useLayoutContext } from '@/shared/context/layout-context'
import ResearchKitPanel from './researchkit-panel'

const ResearchKitRightPanel: FC<{ order: number }> = ({ order }) => {
  const { view } = useLayoutContext()
  const isHidden = view === 'history'

  return (
    <>
      <HorizontalResizeHandle
        className={classNames({
          hidden: isHidden,
        })}
      />
      <Panel
        id="ide-redesign-researchkit-panel"
        order={order}
        defaultSize={20}
        minSize={10}
        maxSize={40}
        className={classNames('ide-redesign-researchkit-panel', {
          hidden: isHidden,
        })}
      >
        <div className="ide-redesign-researchkit-panel-inner">
          <ResearchKitPanel />
        </div>
      </Panel>
    </>
  )
}

export default ResearchKitRightPanel
