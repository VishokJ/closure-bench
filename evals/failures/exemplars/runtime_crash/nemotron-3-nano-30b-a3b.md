# runtime_crash: nvidia/nemotron-3-nano-30b-a3b

Rollout `nemotron-3-nano-30b-a3b/R17/5` (/Users/vishokj/Developer/cb-probe/outputs/official/nemotron/closure-bench--nvidia--nemotron-3-nano-30b-a3b--null--aded5d0b/traces.jsonl:182), task R17, grade status `runtime_error`. Picked as the median submission length (3166 chars) of 1 rollouts in this category for this model.

Sub-label: `None`

## Evidence

```json
{
 "note": "runtime_error with no $fatal/$stop/$error from the testbench in the log",
 "run_s": 0.01
}
```

## Gold excerpt (formal witness)

```systemverilog
// gold_source: formal
// closure_core.formal.cover_witness: depth 232, input_changes 12, bound 300, witness 074bc08f805649ef
// Formal witness for R17_rx_double_overrun_third_word (closure_core/formal.py): the shortest legal input
// trace Yosys/SymbiYosys found (232 cycles), replayed on the uart_rx ports.
// A gold candidate, never shown to an agent; Verilator decides whether it hits.
`timescale 1ns / 1ps

module tb;
  logic clk = 1'b0;
  always #5 clk = ~clk;
  logic rst = 1'd1;
  logic rxd = 1'd0;
  logic m_axis_tready = 1'd0;
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
    repeat (18) @(negedge clk);
    rxd = 1'd1;
    repeat (58) @(negedge clk);
    rxd = 1'd0;
    repeat (75) @(negedge clk);
    rxd = 1'd1;
    @(negedge clk);
    rxd = 1'd0;
    repeat (19) @(negedge clk);
    rxd = 1'd1;
    repeat (5) @(negedge clk);
    rxd = 1'd0;
    repeat (11) @(negedge clk);
    rxd = 1'd1;
    repeat (9) @(negedge clk);
    rxd = 1'd0;
    repeat (11) @(negedge clk);
    rxd = 1'd1;
    repeat (5) @(negedge clk);
    rxd = 1'd0;
    repeat (14) @(negedge clk);
    rxd = 1'd1;
    repeat (6) @(negedge clk);
    $finish;
  end
endmodule
```

Event logs and divergence: not replayed (only miss, self_check_failed and never_finishes are).

## Submission excerpt

```systemverilog
module tb;

  // -------------------------------------------------
  // Clock generation
  // -------------------------------------------------
  logic        clk = 0;
  initial begin
    forever #5 clk = ~clk;
  end

  // -------------------------------------------------
  // Reset and configuration
  // -------------------------------------------------
  logic        rst = 1'b0;
  logic [15:0] prescale = 16'd5;   // default prescale used in the regression

  // -------------------------------------------------
  // UART interface signals
  // -------------------------------------------------
  logic        rxd = 1'b1;

  // AXI‑Stream slave side (unused – just tie off)
  logic [7:0]  s_axis_tdata = '0;
  logic        s_axis_tvalid = 1'b0;

  // AXI‑Stream master side – we only observe
  logic [7:0]  m_axis_tdata;
  logic        m_axis_tvalid;
  logic        m_axis_tready;   // hold low forever

  // UART line and status signals
  logic        txd;
  logic        tx_busy;
  logic        rx_busy;
  logic        rx_overrun_error;
  logic        rx_frame_error;

  // -------------------------------------------------
  // Keep m_axis_tready permanently low
  // -------------------------------------------------
  initial begin
    m_axis_tready = 1'b0;
    forever #0 m_axis_tready = 1'b0;
  end

  // -------------------------------------------------
  // DUT instantiation (uart top‑level)
  // -------------------------------------------------
  uart #(.DATA_WIDTH(8)) dut (
    .clk          (clk),
    .rst          (rst),
    .s_axis_tdata (s_axis_tdata),
    .s_axis_tvalid(s_axis_tvalid),
    .s_axis_tready(),          // not connected
    .m_axis_tdata (m_axis_tdata),
    .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready),
    .txd          (txd),
    .tx_busy      (tx_busy),
    .rx_busy      (rx_busy),
    .rx_overrun_error (rx_overrun_error),
    .rx_frame_error   (rx_frame_error),
    .prescale     (prescale)
  );

  // -------------------------------------------------
  // Reset task
  // -------------------------------------------------
  task automatic do_reset;
    rst = 1'b0;
    #20;
    rst = 1'b1;
    #20;
    rst = 1'b0;
    #20;
  endtask

  // -------------------------------------------------
  // Task to present one UART byte on rxd
  // -------------------------------------------------
```
