import { useState } from 'react'
import { Plus } from 'lucide-react'
import { Button } from '@components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@components/ui/dialog'

export function EnrollAgentHelp() {
  const [open, setOpen] = useState(false)

  return (
    <>
      <Button onClick={() => setOpen(true)}>
        <Plus className="mr-2 h-4 w-4" />
        Enroll Agent
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>Enroll a Windows endpoint</DialogTitle>
            <DialogDescription>
              An agent is a small program that runs on each computer you want SentinelWatch to monitor.
              It sends process, service, startup, and available Windows event data to this dashboard.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 text-sm text-muted-foreground">
            <p>
              This button opens setup guidance; it does not install software on another computer.
              To enroll a device, install and run the SentinelWatch agent on that device.
            </p>
            <ol className="list-decimal space-y-2 pl-5">
              <li>Configure the agent with the backend address and its enrollment credential.</li>
              <li>Keep the credential in the <code>SW_AGENT_AGENT__ENROLLMENT_TOKEN</code> environment variable; never put it in source code or share it in chat.</li>
              <li>Start the agent. It registers with the backend and begins sending telemetry; this page refreshes automatically.</li>
            </ol>
            <p className="rounded-md border border-border bg-muted/40 p-3">
              This local backend currently listens only on this computer at <code>127.0.0.1:8001</code>.
              Other computers cannot reach it until you deliberately configure a trusted network address and secure transport.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
