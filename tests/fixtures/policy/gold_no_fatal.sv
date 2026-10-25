// R1 gold that cannot fail (frame error).
// Proves the target is reachable with legitimate stimulus: one 8N1 frame
// whose stop bit is driven low. Self-checking: fails unless frame_error pulses.
`timescale 1ns / 1ps

module tb;

  localparam logic [15:0] PRESCALE = 16'd5;

  logic        clk = 1'b0;
  logic        rst = 1'b0;
  logic        rxd = 1'b1;
  wire  [7:0]  m_axis_tdata;
  wire         m_axis_tvalid, busy, overrun_error, frame_error;

  always #4 clk = ~clk;

  uart_rx #(.DATA_WIDTH(8)) dut (
    .clk(clk), .rst(rst),
    .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid), .m_axis_tready(1'b1),
    .rxd(rxd), .busy(busy), .overrun_error(overrun_error), .frame_error(frame_error),
    .prescale(PRESCALE)
  );

  // Drive on the falling edge so inputs are stable at every rising edge.
  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  task automatic send_frame(input byte unsigned b, input bit stop);
    int bit_clks = int'(PRESCALE) * 8;
    rxd = 1'b0;   wait_clks(bit_clks);              // start
    for (int i = 0; i < 8; i++) begin rxd = b[i]; wait_clks(bit_clks); end
    rxd = stop;   wait_clks(bit_clks);              // stop bit (0 = framing error)
    rxd = 1'b1;   wait_clks(bit_clks);              // back to idle
  endtask

  bit saw_frame_error = 0;
  always @(posedge clk) if (frame_error) saw_frame_error <= 1;

  initial begin
    rst = 1'b1; wait_clks(2);
    rst = 1'b0; wait_clks(2);
    send_frame(8'h55, 1'b0);
    if (!saw_frame_error) $display("frame_error never pulsed");
    $display("PASS gold R1");
    $finish;
  end

endmodule
