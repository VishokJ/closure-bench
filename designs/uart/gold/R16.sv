// gold_source: formal
// closure_core.formal.cover_witness: depth 234, input_changes 29, bound 300, witness e1b859bce533cff4
// Formal witness for R16_rx_prescale_change_between_frames (closure_core/formal.py): the shortest legal input
// trace Yosys/SymbiYosys found (234 cycles), replayed on the uart_rx ports.
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
    repeat (4) @(negedge clk);
    rxd = 1'd1;
    repeat (10) @(negedge clk);
    rxd = 1'd0;
    repeat (13) @(negedge clk);
    rxd = 1'd1;
    @(negedge clk);
    rxd = 1'd0;
    repeat (2) @(negedge clk);
    rxd = 1'd1;
    repeat (3) @(negedge clk);
    rxd = 1'd0;
    repeat (15) @(negedge clk);
    rxd = 1'd1;
    repeat (5) @(negedge clk);
    rxd = 1'd0;
    repeat (12) @(negedge clk);
    m_axis_tready = 1'd0;
    repeat (2) @(negedge clk);
    rxd = 1'd1;
    repeat (5) @(negedge clk);
    m_axis_tready = 1'd1;
    repeat (5) @(negedge clk);
    m_axis_tready = 1'd0;
    @(negedge clk);
    rxd = 1'd0; m_axis_tready = 1'd1;
    @(negedge clk);
    m_axis_tready = 1'd0; prescale = 16'd2;
    @(negedge clk);
    rxd = 1'd1;
    repeat (3) @(negedge clk);
    rxd = 1'd0;
    repeat (19) @(negedge clk);
    rxd = 1'd1;
    repeat (19) @(negedge clk);
    rxd = 1'd0;
    repeat (13) @(negedge clk);
    rxd = 1'd1;
    repeat (32) @(negedge clk);
    rxd = 1'd0;
    repeat (27) @(negedge clk);
    m_axis_tready = 1'd1;
    repeat (2) @(negedge clk);
    rxd = 1'd1;
    repeat (3) @(negedge clk);
    rxd = 1'd0;
    @(negedge clk);
    rxd = 1'd1;
    repeat (2) @(negedge clk);
    rxd = 1'd0;
    repeat (14) @(negedge clk);
    rxd = 1'd1;
    repeat (19) @(negedge clk);
    $finish;
  end
endmodule
