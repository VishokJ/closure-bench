// gold_source: formal
// closure_core.formal.cover_witness: depth 156, input_changes 20, bound 300, witness 593d3cc885e20e90
// Formal witness for R15_rx_glitch_off_sample_point_ignored (closure_core/formal.py): the shortest legal input
// trace Yosys/SymbiYosys found (156 cycles), replayed on the uart_rx ports.
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
    repeat (8) @(negedge clk);
    rxd = 1'd1;
    repeat (11) @(negedge clk);
    rxd = 1'd0;
    repeat (2) @(negedge clk);
    rxd = 1'd1;
    repeat (12) @(negedge clk);
    rxd = 1'd0;
    repeat (4) @(negedge clk);
    rxd = 1'd1;
    repeat (5) @(negedge clk);
    rxd = 1'd0;
    repeat (8) @(negedge clk);
    rxd = 1'd1;
    repeat (7) @(negedge clk);
    rxd = 1'd0;
    repeat (10) @(negedge clk);
    rxd = 1'd1;
    repeat (9) @(negedge clk);
    rxd = 1'd0;
    repeat (6) @(negedge clk);
    rxd = 1'd1;
    repeat (2) @(negedge clk);
    rxd = 1'd0;
    repeat (5) @(negedge clk);
    rxd = 1'd1;
    repeat (7) @(negedge clk);
    rxd = 1'd0;
    repeat (13) @(negedge clk);
    rxd = 1'd1;
    repeat (13) @(negedge clk);
    rxd = 1'd0;
    repeat (10) @(negedge clk);
    rxd = 1'd1;
    repeat (5) @(negedge clk);
    rxd = 1'd0;
    repeat (9) @(negedge clk);
    rxd = 1'd1;
    repeat (10) @(negedge clk);
    $finish;
  end
endmodule
