import { PageHeader } from './PageHeader'

/** Порожня сторінка-заглушка, яку заміняє справжній екран у наступних спринтах. */
export function StubPage({ title, note }: { title: string; note: string }) {
  return (
    <>
      <PageHeader title={title} subtitle={note} />
      <div className="stub">
        <div>
          <p className="stub__title">Заготовка екрана</p>
          <p className="caption">Макет у розробці</p>
        </div>
      </div>
    </>
  )
}
