# policy_violation: nvidia/nemotron-3-nano-30b-a3b

Rollout `nemotron-3-nano-30b-a3b/R20/0` (/Users/vishokj/Developer/cb-probe/outputs/official/nemotron/closure-bench--nvidia--nemotron-3-nano-30b-a3b--null--aded5d0b/traces.jsonl:76), task R20, grade status `policy_violation`. Picked as the median submission length (6607 chars) of 1 rollouts in this category for this model.

Sub-label: `file I/O (waveform dump) is not allowed in a testbench`

## Evidence

```json
{
 "diagnostic": "<work>/submission/tb.sv:141: file I/O (waveform dump) is not allowed in a testbench"
}
```

## Gold excerpt (formal witness)

```systemverilog
// gold_source: formal
// closure_core.formal.cover_witness: depth 157, input_changes 14, bound 300, witness 4f445d7512ef6b54
// Formal witness for R20_rx_single_cycle_stall_accept (closure_core/formal.py): the shortest legal input
// trace Yosys/SymbiYosys found (157 cycles), replayed on the uart_rx ports.
// A gold candidate, never shown to an agent; Verilator decides whether it hits.
`timescale 1ns / 1ps

module tb;
  logic clk = 1'b0;
  always #5 clk = ~clk;
  logic rst = 1'd1;
  logic rxd = 1'd0;
  logic m_axis_tready = 1'd1;
  logic [15:0] prescale = 16'd1;
  wire  [7:0] m_axis_tdata;
  wire  m_axis_tvalid;
  wire  busy;
  wire  overrun_error;
  wire  frame_error;

  uart_rx dut (.clk(clk), .rst(rst), .rxd(rxd), .m_axis_tready(m_axis_tready), .prescale(prescale), .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid), .busy(busy), .overrun_error(overrun_error), .frame_error(frame_error));

  initial begin
    @(negedge clk);
    rst = 1'd0;
    repeat (27) @(negedge clk);
    rxd = 1'd1;
    repeat (30) @(negedge clk);
    rxd = 1'd0;
    repeat (18) @(negedge clk);
    rxd = 1'd1;
    @(negedge clk);
    rxd = 1'd0;
    repeat (5) @(negedge clk);
    rxd = 1'd1;
    repeat (7) @(negedge clk);
    rxd = 1'd0;
    repeat (9) @(negedge clk);
    rxd = 1'd1; m_axis_tready = 1'd0;
    repeat (11) @(negedge clk);
    rxd = 1'd0;
    repeat (13) @(negedge clk);
    rxd = 1'd1;
    repeat (13) @(negedge clk);
    rxd = 1'd0;
    repeat (8) @(negedge clk);
    rxd = 1'd1;
    repeat (12) @(negedge clk);
    m_axis_tready = 1'd1;
    repeat (3) @(negedge clk);
    $finish;
  end
endmodule
```

Event logs and divergence: not replayed (only miss, self_check_failed and never_finishes are).

## Submission excerpt

```systemverilog
`timescale 1ns/1ps
module tb;

  // --------------------------------------------------------------
  // Parameters and clock generation
  // --------------------------------------------------------------
  localparam int CLK_PERIOD = 8;                 // 125 MHz
  localparam logic [15:0] PRESCALE = 16'd5;      // default prescale

  logic        clk = 0;
  always #(CLK_PERIOD/2) clk = ~clk;           // toggle every half‑period

  // --------------------------------------------------------------
  // Reset handling
  // --------------------------------------------------------------
  logic        rst = 1;
  initial begin
    #20 rst = 0;
    #20 rst = 1;
    #20 rst = 0;
  end

  // --------------------------------------------------------------
  // DUT interlock signals
  // --------------------------------------------------------------
  logic [15:0] prescale = PRESCALE;

  // AXI‑Stream input side (unused – tie off)
  logic [7:0]  s_axis_tdata  = 8'h00;
  logic        s_axis_tvalid = 1'b0;
  logic        s_axis_tready;                  // output, just connect to a wire

  // AXI‑Stream output side (monitor)
  logic [7:0]  m_axis_tdata;
  logic        m_axis_tvalid;
  logic        m_axis_tready;                  // <-- we drive this directly
  logic [7:0]  txd;
  logic        tx_busy;
  logic        rx_busy;
  logic        rx_overrun_error;
  logic        rx_frame_error;

  // UART interface
  logic        rxd = 1'b1;                     // <-- we drive this

  // --------------------------------------------------------------
  // Bind the DUT (uart) – all ports are connected by name
  // --------------------------------------------------------------
  uart #(.DATA_WIDTH(8)) dut (
    .clk               (clk),
    .rst               (rst),
    .s_axis_tdata      (s_axis_tdata),
    .s_axis_tvalid     (s_axis_tvalid),
    .s_axis_tready     (s_axis_tready),   // unused output
    .m_axis_tdata      (m_axis_tdata),
    .m_axis_tvalid     (m_axis_tvalid),
    .m_axis_tready     (m_axis_tready),   // <-- driven externally
    .rxd               (rxd),
    .txd               (txd),
    .tx_busy           (tx_busy),
    .rx_busy           (rx_busy),
    .rx_overrun_error  (rx_overrun_error),
    .rx_frame_error    (rx_frame_error),
    .prescale          (prescale)
  );

  // --------------------------------------------------------------
  // Helper tasks
  // --------------------------------------------------------------
  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  task automatic send_byte(input byte unsigned b);
    int bit_clks = int'(prescale) * 8;
    // start bit
    rxd = 1'b0; wait_clks(bit_clks);
    // data bits, LSB first
    for (int i = 0; i < 8; i++) begin
      rxd = b[i];
```
